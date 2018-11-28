#!/usr/bin/env escript
%%! -name create_storage@test_env

-export([main/1]).

main([Cookie, Node, Name, ClusterName, MonitorHostname, PoolName, Username,
    Key, Insecure, StoragePathType]) ->

    erlang:set_cookie(node(), list_to_atom(Cookie)),
    NodeAtom = list_to_atom(Node),

    UserCtx = #{
        <<"username">> => list_to_binary(Username),
        <<"key">> => list_to_binary(Key)
    },
    Helper = safe_call(NodeAtom, helper, new_helper, [
        <<"ceph">>,
        #{
            <<"monitorHostname">> => list_to_binary(MonitorHostname),
            <<"clusterName">> => list_to_binary(ClusterName),
            <<"poolName">> => list_to_binary(PoolName)
        },
        UserCtx,
        list_to_atom(Insecure),
        list_to_binary(StoragePathType)
    ]),

    StorageDoc = safe_call(NodeAtom, storage, new, [list_to_binary(Name), [Helper]]),
    safe_call(NodeAtom, storage, create, [StorageDoc]).

safe_call(Node, Module, Function, Args) ->
    case rpc:call(Node, Module, Function, Args) of
        {badrpc, X} ->
            io:format(standard_error, "ERROR: in module ~p:~n {badrpc, ~p} in rpc:call(~p, ~p, ~p, ~p).~n",
                [?MODULE, X, Node, Module, Function, Args]),
            halt(42);
        {error, X} ->
            io:format(standard_error, "ERROR: in module ~p:~n {error, ~p} in rpc:call(~p, ~p, ~p, ~p).~n",
                [?MODULE, X, Node, Module, Function, Args]),
            halt(42);
        X ->
            X
    end.
