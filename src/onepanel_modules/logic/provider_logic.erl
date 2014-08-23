%% ===================================================================
%% @author Krzysztof Trzepla
%% @copyright (C): 2014 ACK CYFRONET AGH
%% This software is released under the MIT license
%% cited in 'LICENSE.txt'.
%% @end
%% ===================================================================
%% @doc: This module contains Global Registry interaction functions.
%% It allows to create Certificate Signing Request and register in
%% Global Registry (gr for short).
%% @end
%% ===================================================================
-module(provider_logic).

-include("registered_names.hrl").
-include("onepanel_modules/installer/state.hrl").
-include("onepanel_modules/installer/internals.hrl").
-include("onepanel_modules/logic/provider_logic.hrl").
-include_lib("ctool/include/logging.hrl").

%% API
-export([register/0, unregister/0, create_csr/3]).
-export([get_ports_to_check/0, get_provider_id/0]).

-on_load(init/0).

%% ====================================================================
%% API functions
%% ====================================================================

%% init/0
%% ====================================================================
%% @doc Initializes NIF library used to create Certificate Signing Request.
%% @end
-spec init() -> ok | no_return().
%% ====================================================================
init() ->
    ok = erlang:load_nif("c_lib/provider_logic_drv", 0).


%% create_csr/3
%% ====================================================================
%% @doc Call underlying NIF function. Creates private key and certificate
%% signing request and saves them at given paths.
%% Returns 0 in case of success and 1 in case of failure.
%% Can throw an exception if nif was not properly loaded.
%% @end
-spec create_csr(Password :: string(), KeyFile :: string(), CsrPath :: string()) -> Result when
    Result :: 0 | 1 | no_return().
%% ====================================================================
create_csr(_, _, _) ->
    throw("NIF library not loaded.").


%% register/0
%% ====================================================================
%% @doc Registers provider in Global Registry. In case of successful
%% registration generated private key and certificate are save on all
%% hosts. Returns provider ID or an error.
%% @end
-spec register() -> Result when
    Result :: {ok, ProviderId :: binary()} | {error, Reason :: term()}.
%% ====================================================================
register() ->
    try
        {ok, KeyFile} = application:get_env(?APP_NAME, grpkey_path),
        {ok, KeyName} = application:get_env(?APP_NAME, grpkey_name),
        {ok, CsrPath} = application:get_env(?APP_NAME, grpcsr_file),
        {ok, CertName} = application:get_env(?APP_NAME, grpcert_name),
        {ok, CertFile} = application:get_env(?APP_NAME, grpcert_path),
        Path = filename:join([?DEFAULT_NODES_INSTALL_PATH, ?DEFAULT_WORKER_NAME, "certs"]),

        0 = create_csr("", KeyFile, CsrPath),

        %% Save private key on all hosts
        {ok, Key} = file:read_file(KeyFile),
        ok = onepanel_utils:save_file_on_hosts(Path, KeyName, Key),

        %% Register in Global Registry
        {ok, CSR} = file:read_file(CsrPath),
        {ok, [ControlPanelHost | _]} = onepanel_utils:get_control_panel_hosts(),
        {ok, ControlPanelHostIpAddress} = rpc:call(onepanel_utils:get_node(ControlPanelHost), gr_providers, check_ip_address, [provider, ?CONNECTION_TIMEOUT]),
        {ok, #?LOCAL_CONFIG_RECORD{gui_port = GuiPort}} = dao:get_record(?LOCAL_CONFIG_TABLE, ControlPanelHost),
        URLs = lists:map(fun(Host) ->
            {ok, IpAddress} = rpc:call(onepanel_utils:get_node(Host), gr_providers, check_ip_address, [provider, ?CONNECTION_TIMEOUT]),
            IpAddress
        end, onepanel_utils:get_hosts()),
        RedirectionPoint = <<"https://", ControlPanelHostIpAddress/binary, ":", (integer_to_binary(GuiPort))/binary>>,
        Parameters = [{<<"urls">>, URLs}, {<<"csr">>, CSR}, {<<"redirectionPoint">>, RedirectionPoint}],
        {ok, ProviderId, Cert} = gr_providers:register(provider, Parameters),

        %% Save provider ID and certifiacte on all hosts
        ok = file:write_file(CertFile, Cert),
        ok = onepanel_utils:save_file_on_hosts(Path, CertName, Cert),
        ok = dao:save_record(?PROVIDER_TABLE, #?PROVIDER_RECORD{id = ProviderId, urls = URLs, redirection_point = RedirectionPoint}),

        {ok, ProviderId}
    catch
        _:Reason ->
            ?error("Cannot register in Global Registry: ~p", [Reason]),
            {error, Reason}
    end.


%% unregister/0
%% ====================================================================
%% @doc Unregisters provider from Global Registry and removes his details
%% from database.
%% @end
-spec unregister() -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
unregister() ->
    try
        ProviderId = get_provider_id(),
        ok = gr_providers:unregister(provider),
        ok = dao:delete_record(?PROVIDER_TABLE, ProviderId)
    catch
        _:Reason ->
            ?error("Cannot unregister from Global Registry: ~p", [Reason]),
            {error, Reason}
    end.


%% get_ports_to_check/0
%% ====================================================================
%% @doc Returns default veilcluster ports that will be checked by Global Registry
-spec get_ports_to_check() -> Result when
    Result :: {ok, Ports :: [{Type :: string(), Port :: integer()}]} | {error, Reason :: term()}.
%% ====================================================================
get_ports_to_check() ->
    try
        {ok, #?GLOBAL_CONFIG_RECORD{main_ccm = MainCCM}} = dao:get_record(?GLOBAL_CONFIG_TABLE, ?CONFIG_ID),
        Node = list_to_atom("ccm@" ++ MainCCM),
        {ok, GuiPort} = rpc:call(Node, application, get_env, [veil_cluster_node, control_panel_port]),
        {ok, RestPort} = rpc:call(Node, application, get_env, [veil_cluster_node, rest_port]),
        {ok, [{"gui", GuiPort}, {"rest", RestPort}]}
    catch
        _:Reason ->
            ?error("Cannot get ports to check: ~p", [Reason]),
            {error, Reason}
    end.


%% get_provider_id/0
%% ====================================================================
%% @doc Returns provider ID.
-spec get_provider_id() -> Result when
    Result :: undefined | binary().
%% ====================================================================
get_provider_id() ->
    case dao:get_records(?PROVIDER_TABLE) of
        {ok, [#?PROVIDER_RECORD{id = ProviderId} | _]} ->
            ProviderId;
        _ ->
            undefined
    end.
