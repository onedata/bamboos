%% ===================================================================
%% @author Krzysztof Trzepla
%% @copyright (C): 2014 ACK CYFRONET AGH
%% This software is released under the MIT license
%% cited in 'LICENSE.txt'.
%% @end
%% ===================================================================
%% @doc This module contains utility installation functions.
%% @end
%% ===================================================================
-module(installer_utils).

-include("registered_names.hrl").
-include("onepanel_modules/installer/state.hrl").
-include("onepanel_modules/installer/internals.hrl").
-include_lib("ctool/include/logging.hrl").

%% API
-export([set_ulimits/2, get_ulimits_cmd/1]).
-export([get_workers/0, get_global_config/0, get_timestamp/0, set_timestamp/0]).
-export([add_node_to_config/3, remove_node_from_config/1, overwrite_config_args/3]).
-export([finalize_installation/1]).

%% Defines how many times onepanel will try to verify software start
-define(FINALIZE_INSTALLATION_ATTEMPTS, 120).

%% Defines how long onepanel will wait before next attempt to verify software start
-define(NEXT_ATTEMPT_DELAY, 1000).

%% ====================================================================
%% API functions
%% ====================================================================


%% set_ulimits/2
%% ====================================================================
%% @doc Sets system limits for open files and processes on local host.
%% @end
-spec set_ulimits(OpenFiles :: integer(), Processes :: integer()) -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
set_ulimits(OpenFiles, Processes) ->
    try
        Host = onepanel_utils:get_host(node()),
        ok = file:write_file(?ULIMITS_CONFIG_PATH, io_lib:fwrite("~p.\n~p.\n", [{open_files, integer_to_list(OpenFiles)}, {process_limit, integer_to_list(Processes)}])),
        ok = dao:update_record(?LOCAL_CONFIG_TABLE, Host, [{open_files_limit, integer_to_list(OpenFiles)}, {processes_limit, integer_to_list(Processes)}])
    catch
        _:Reason ->
            ?error("Cannot set ulimits: ~p", [Reason]),
            {error, Reason}
    end.


%% get_ulimits_cmd/0
%% ====================================================================
%% @doc Returns ulimits command required during database or veil node installation.
%% @end
-spec get_ulimits_cmd(Host :: string()) -> Result when
    Result :: string().
%% ====================================================================
get_ulimits_cmd(Host) ->
    try
        {ok, #?LOCAL_CONFIG_RECORD{open_files_limit = OpenFiles, processes_limit = Processes}} = dao:get_record(?LOCAL_CONFIG_TABLE, Host),
        "ulimit -n " ++ OpenFiles ++ " ; ulimit -u " ++ Processes
    catch
        _:Reason ->
            ?error("Cannot get ulimits configuration: ~p. Returning default values.", [Reason]),
            "ulimit -n " ++ ?DEFAULT_OPEN_FILES ++ " ; ulimit -u " ++ ?DEFAULT_PROCESSES
    end.


%% add_node_to_config/3
%% ====================================================================
%% @doc Adds a node to configured_nodes.cfg.
%% @end
-spec add_node_to_config(Type :: atom(), Name :: string(), Path :: string()) -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
add_node_to_config(Type, Name, Path) ->
    try
        {ok, Entries} = file:consult(?CONFIGURED_NODES_PATH),
        save_nodes_in_config(Entries ++ [{Type, Name, Path}])
    catch
        _:Reason ->
            ?error("Cannot add ~p node to ~s: ~p", [Name, ?CONFIGURED_NODES_PATH, Reason]),
            {error, Reason}
    end.


%% remove_node_from_config/1
%% ====================================================================
%% @doc Removes a node from configured_nodes.cfg.
%% @end
-spec remove_node_from_config(Type :: atom()) -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
remove_node_from_config(Type) ->
    try
        {ok, Entries} = file:consult(?CONFIGURED_NODES_PATH),
        ToDelete = case lists:keyfind(Type, 1, Entries) of
                       false -> ?warning("Node ~p not found among configured nodes.", [Type]);
                       Term -> Term
                   end,
        save_nodes_in_config(Entries -- [ToDelete])
    catch
        _:Reason ->
            ?error("Cannot delete ~p from ~s: ~p", [Type, ?CONFIGURED_NODES_PATH, Reason]),
            {error, Reason}
    end.


%% save_nodes_in_config/1
%% ====================================================================
%% @doc Saves list of nodes in configured_nodes.cfg.
%% @end
-spec save_nodes_in_config(Name :: string()) -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
save_nodes_in_config(NodeList) ->
    try
        file:write_file(?CONFIGURED_NODES_PATH, ""),
        lists:foreach(
            fun(Node) ->
                file:write_file(?CONFIGURED_NODES_PATH, io_lib:fwrite("~p.\n", [Node]), [append])
            end, NodeList),
        ok
    catch
        _:Reason ->
            ?error("Cannot write to ~s: ~p", [?CONFIGURED_NODES_PATH, Reason]),
            {error, Reason}
    end.


%% overwrite_config_args/3
%% ====================================================================
%% @doc Overwrites a parameter in config.args.
%% @end
-spec overwrite_config_args(Path :: string(), Parameter :: string(), NewValue :: string()) -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
overwrite_config_args(Path, Parameter, NewValue) ->
    try
        FileContent = case file:read_file(Path) of
                          {ok, DataRead} ->
                              binary_to_list(DataRead);
                          _ ->
                              throw("Could not read config.args file.")
                      end,

        {match, [{From, Through}]} = re:run(FileContent, Parameter ++ ":.*\n"),
        Beginning = string:substr(FileContent, 1, From),
        End = string:substr(FileContent, From + Through, length(FileContent) - From - Through + 1),
        file:write_file(Path, list_to_binary(Beginning ++ Parameter ++ ": " ++ NewValue ++ End)),
        ok
    catch
        _:Reason ->
            ?error("Cannot overwrite config args: ~p", [Reason]),
            {error, Reason}
    end.


%% get_workers/0
%% ====================================================================
%% @doc Returns configured workers list.
%% @end
-spec get_workers() -> Result when
    Result :: [string()].
%% ====================================================================
get_workers() ->
    case dao:get_record(?GLOBAL_CONFIG_TABLE, ?CONFIG_ID) of
        {ok, #?GLOBAL_CONFIG_RECORD{workers = Workers}} ->
            Workers;
        _ ->
            []
    end.


%% get_global_config/0
%% ====================================================================
%% @doc Returns global installation configuration.
%% @end
-spec get_global_config() -> list().
%% ====================================================================
get_global_config() ->
    case dao:get_record(?GLOBAL_CONFIG_TABLE, ?CONFIG_ID) of
        {ok, Record} ->
            Fields = record_info(fields, ?GLOBAL_CONFIG_RECORD),
            [_ | Values] = tuple_to_list(Record),
            lists:zip(Fields, Values);
        _ -> []
    end.


%% finalize_installation/1
%% ====================================================================
%% @doc Waits until cluster control panel nodes are up and running.
%% Returns an error after ?FINALIZE_INSTALLATION_ATTEMPTS limit.
%% @end
-spec finalize_installation(Args :: [{Name :: atom(), Value :: term()}]) -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
finalize_installation(_Args) ->
    set_timestamp(),
    finalize_installation_loop(?FINALIZE_INSTALLATION_ATTEMPTS).


%% get_timestamp/0
%% ====================================================================
%% @doc Returns timestamp (microseconds since epoch) of last global 
%% configuration change.
%% @end
-spec get_timestamp() -> Result when
    Result :: integer().
%% ====================================================================
get_timestamp() ->
    case dao:get_record(?GLOBAL_CONFIG_TABLE, ?CONFIG_ID) of
        #?GLOBAL_CONFIG_RECORD{timestamp = Timestamp} ->
            Timestamp;
        _ ->
            0
    end.


%% set_timestamp/0
%% ====================================================================
%% @doc Sets timestamp for global configuration to microsecond since 
%% epoch.
%% @end
-spec set_timestamp() -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
set_timestamp() ->
    {MegaSecs, Secs, MicroSecs} = now(),
    Timestamp = 1000000000000 * MegaSecs + 1000000 * Secs + MicroSecs,
    dao:update_record(?GLOBAL_CONFIG_TABLE, ?CONFIG_ID, [{timestamp, Timestamp}]).


%% ====================================================================
%% Internal functions
%% ====================================================================

%% finalize_installation/2
%% ====================================================================
%% @doc Waits until cluster control panel nodes are up and running.
%% Returns an error after ?FINALIZE_INSTALLATION_ATTEMPTS limit.
%% Should not be used directly, use finalize_installation/1 instead.
%% @end
-spec finalize_installation_loop(Attempts :: integer()) -> Result when
    Result :: ok | {error, Reason :: term()}.
%% ====================================================================
finalize_installation_loop(0) ->
    ?error("Cannot finalize installation: attempts limit exceeded."),
    {error, <<"Attempts limit exceeded.">>};

finalize_installation_loop(Attempts) ->
    case onepanel_utils:get_control_panel_hosts() of
        {ok, [_ | _]} ->
            ok;
        _ ->
            timer:sleep(?NEXT_ATTEMPT_DELAY),
            finalize_installation_loop(Attempts - 1)
    end.