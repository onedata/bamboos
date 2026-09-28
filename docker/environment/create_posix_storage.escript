#!/usr/bin/env escript
%%! -name create_storage@test_env

-export([main/1]).

main([Cookie, Node, Name, MountPoint, StoragePathType]) ->
    erlang:set_cookie(node(), list_to_atom(Cookie)),
    NodeAtom = list_to_atom(Node),

    CredentialsParams = #{
        <<"uid">> => <<"0">>,
        <<"gid">> => <<"0">>
    },
    safe_call(NodeAtom, initializer, create_storage, [
        list_to_binary(Name),
        <<"posix">>,
        #{
            <<"mountPoint">> => list_to_binary(MountPoint),
            <<"storagePathType">> => list_to_binary(StoragePathType)
        },
        CredentialsParams
    ]).

safe_call(Node, Module, Function, Args) ->
    true = net_kernel:hidden_connect_node(Node),
    case rpc:call(Node, Module, Function, Args) of
        {badrpc, X} ->
            io:format(standard_error, "ERROR: in module ~tp:~n {badrpc, ~tp} in rpc:call(~tp, ~tp, ~tp, ~tp).~n",
                [?MODULE, X, Node, Module, Function, Args]),
            halt(42);
        {error, X} ->
            io:format(standard_error, "ERROR: in module ~tp:~n {error, ~tp} in rpc:call(~tp, ~tp, ~tp, ~tp).~n",
                [?MODULE, X, Node, Module, Function, Args]),
            halt(42);
        X ->
            X
    end.
