%% ===================================================================
%% @author Lukasz Opiola
%% @copyright (C): 2013 ACK CYFRONET AGH
%% This software is released under the MIT license
%% cited in 'LICENSE.txt'.
%% @end
%% ===================================================================
%% @doc: This file contains n2o website code.
%% The page handles user validation via OpenID.
%% @end
%% ===================================================================

-module(page_validate_login).
-export([main/0, event/1]).
-include("gui_modules/common.hrl").
-include_lib("ctool/include/logging.hrl").

%% ====================================================================
%% API functions
%% ====================================================================

%% main/0
%% ====================================================================
%% @doc Template points to the template file, which will be filled with content.
-spec main() -> Result when
    Result :: #dtl{}.
%% ====================================================================
main() ->
    #dtl{file = "bare", app = ?APP_NAME, bindings = [{title, title()}, {body, body()}, {custom, <<"">>}]}.


%% title/0
%% ====================================================================
%% @doc Page title.
-spec title() -> Result when
    Result :: binary().
%% ====================================================================
title() -> <<"Login validation">>.


%% body/0
%% ====================================================================
%% @doc This will be placed instead of {{body}} tag in template.
-spec body() -> Result when
    Result :: no_return().
%% ====================================================================
body() ->
    case gui_ctx:user_logged_in() of
        true -> gui_jq:redirect(<<"/">>);
        false ->
            {ok, Params} = gui_ctx:form_params(),
            Username = proplists:get_value(<<"username">>, Params),
            Password = proplists:get_value(<<"password">>, Params),
            case user_logic:authenticate(Username, Password) of
                ok ->
                    ?info("Successful login of user: ~p", [Username]),
                    gui_ctx:create_session(),
                    gui_ctx:set_user_id(Username),
                    gui_jq:redirect_from_login();
                {error, Reason} ->
                    ?error("Invalid login attemp, user ~p: ~p", [Username, Reason]),
                    gui_jq:redirect(<<"/login?id=", (gui_str:to_binary(Reason))/binary>>)
            end
    end.


%% ====================================================================
%% Events handling
%% ====================================================================

%% event/1
%% ====================================================================
%% @doc Handles page events.
-spec event(Event :: term()) -> no_return().
%% ====================================================================
event(init) -> ok;

event(terminate) -> ok.