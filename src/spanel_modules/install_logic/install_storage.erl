%% ===================================================================
%% @author Krzysztof Trzepla
%% @copyright (C): 2014 ACK CYFRONET AGH
%% This software is released under the MIT license
%% cited in 'LICENSE.txt'.
%% @end
%% ===================================================================
%% @doc: This file contains storage installation functions
%% @end
%% ===================================================================
-module(install_storage).

-include("registered_names.hrl").
-include("spanel_modules/install.hrl").
-include("spanel_modules/db.hrl").

%% API
-export([create_storage_test_file/1, delete_storage_test_file/1, check_storage_on_host/2, check_storage_on_hosts/2]).
-export([add_storage_paths/1, remove_storage_paths/1, add_storage_paths_on_hosts/2, remove_storage_paths_on_hosts/2]).

-define(STORAGE_TEST_FILE_PREFIX, "storage_test_").
-define(STORAGE_TEST_FILE_LENGTH, 20).

%% ====================================================================
%% @doc Creates new path for storage test file. If path already exists new one is generated.
-spec create_storage_test_file(Path :: string()) -> {ok, FilePath :: string(), Content :: string} | error.
%% ====================================================================
create_storage_test_file(Path) ->
  create_storage_test_file(Path, 20).

create_storage_test_file(_, 0) ->
  error;
create_storage_test_file(Path, Attempts) ->
  {A, B, C} = now(),
  random:seed(A, B, C),
  Filename = install_utils:random_ascii_lowercase_sequence(8),
  FilePath = Path ++ "/" ++ ?STORAGE_TEST_FILE_PREFIX ++ Filename,
  try
    {ok, Fd} = file:open(FilePath, [write, exclusive]),
    Content = install_utils:random_ascii_lowercase_sequence(?STORAGE_TEST_FILE_LENGTH),
    ok = file:write(Fd, Content),
    ok = file:close(Fd),
    {ok, FilePath, Content}
  catch
    _:_ -> create_storage_test_file(Path, Attempts - 1)
  end.

%% ====================================================================
%% @doc Deletes storage test file.
-spec delete_storage_test_file(FilePath :: string()) -> ok | {error, Error :: term()}.
%% ====================================================================
delete_storage_test_file(FilePath) ->
  case file:delete(FilePath) of
    ok -> ok;
    {error, Error} ->
      lager:error("Error while deleting storage test file: ~p", [Error]),
      {error, Error}
  end.

%% check_storage_on_hosts/1
%% ====================================================================
%% @doc Checks storage availability on hosts. Returns ok or first host for which
%% storage is not available.
%% @end
-spec check_storage_on_hosts(Hosts :: [string()], Path :: string()) -> ok | {error, ErrorHosts :: [string()]}.
%% ====================================================================
check_storage_on_hosts([], _) ->
  ok;
check_storage_on_hosts([Host | Hosts], Path) ->
  case gen_server:call({?SPANEL_NAME, install_utils:get_node(Host)}, {create_storage_test_file, Path}, ?GEN_SERVER_TIMEOUT) of
    {ok, FilePath, Content} ->
      try
        Answer = lists:foldl(fun
          (H, {NewContent, ErrorHosts}) ->
            case gen_server:call({?SPANEL_NAME, install_utils:get_node(H)}, {check_storage, FilePath, NewContent}, ?GEN_SERVER_TIMEOUT) of
              {ok, NextContent} -> {NextContent, ErrorHosts};
              {error, ErrorHost} -> {NewContent, [ErrorHost | ErrorHosts]}
            end
        end, {Content, []}, [Host | Hosts]),
        gen_server:cast({?SPANEL_NAME, install_utils:get_node(Host)}, {delete_storage_test_file, FilePath}),
        case Answer of
          {_, []} -> ok;
          {_, EHosts} -> {error, EHosts}
        end
      catch
        _:_ ->
          gen_server:cast({?SPANEL_NAME, install_utils:get_node(Host)}, {delete_storage_test_file, FilePath}),
          error
      end;
    _ -> error
  end.

%% check_storage_on_host/2
%% ====================================================================
%% @doc Checks storage availability on node
%% @end
-spec check_storage_on_host(FilePath :: string(), Content :: string()) -> {ok, NewContent :: string()} | {error, Host :: string()}.
%% ====================================================================
check_storage_on_host(FilePath, Content) ->
  try
    {ok, FdRead} = file:open(FilePath, [read]),
    {ok, Content} = file:read_line(FdRead),
    ok = file:close(FdRead),
    {ok, FdWrite} = file:open(FilePath, [write]),
    NewContent = install_utils:random_ascii_lowercase_sequence(?STORAGE_TEST_FILE_LENGTH),
    ok = file:write(FdWrite, NewContent),
    ok = file:close(FdWrite),
    {ok, NewContent}
  catch
    _:_ -> {error, install_utils:get_host(node())}
  end.

%% remove_storage_paths_on_hosts/1
%% ====================================================================
%% @doc Removes storage configuration on hosts
%% @end
-spec remove_storage_paths_on_hosts(Hosts :: [string()], Paths :: [string()]) -> ok | {error, ErrorHosts :: [string()]}.
%% ====================================================================
remove_storage_paths_on_hosts(Hosts, Paths) ->
  try
    InstalledStorage = case dao:get_record(configurations, last) of
                         {ok, #configuration{storage_paths = StoragePaths}} -> StoragePaths;
                         _ -> []
                       end,

    lists:foreach(fun(Path) ->
      case lists:member(Path, InstalledStorage) of
        true -> ok;
        _ -> throw(<<"Path: ", (list_to_binary(Path))/binary, " is not configured.">>)
      end
    end, Paths),

    {UninstallOk, UninstallError} = install_utils:apply_on_hosts(Hosts, ?MODULE, remove_storage_paths, [Paths], ?RPC_TIMEOUT),

    NewStoragePaths = lists:filter(fun(StoragePath) ->
      not lists:member(StoragePath, Paths) end, InstalledStorage),

    case dao:update_record(configurations, #configuration{id = last, storage_paths = {force, NewStoragePaths}}) of
      ok ->
        case UninstallError of
          [] -> ok;
          _ -> {error, UninstallError}
        end;
      _ ->
        lager:error("Error while updating storage configuration."),
        {error, Hosts}
    end
  catch
    _:Reason -> {error, Reason}
  end.

%% remove_storage_paths/1
%% ====================================================================
%% @doc Removes storage configuration on host
%% @end
-spec remove_storage_paths(Paths :: [string()]) -> ok | error.
%% ====================================================================
remove_storage_paths(Paths) ->
  StorageConfig = ?DEFAULT_NODES_INSTALL_PATH ++ ?DEFAULT_WORKER_NAME ++ "/" ++ ?STORAGE_CONFIG_PATH,
  try
    {ok, StorageInfo} = file:consult(StorageConfig),
    NewPaths = lists:foldl(fun([[{name, cluster_fuse_id}, {root, Path}]], Acc) ->
      case lists:member(Path, Paths) of
        true -> Acc;
        false -> [Path | Acc]
      end
    end, [], StorageInfo),
    ok = file:delete(StorageConfig),
    ok = add_storage_paths(NewPaths),
    ok
  catch
    _:_ -> error
  end.

%% add_storage_paths/1
%% ====================================================================
%% @doc Adds storage configuration on host
%% @end
-spec add_storage_paths(Paths :: [string()]) -> ok | error.
%% ====================================================================
add_storage_paths(Paths) ->
  lager:info("Adding storage paths..."),
  StorageConfig = ?DEFAULT_NODES_INSTALL_PATH ++ ?DEFAULT_WORKER_NAME ++ "/" ++ ?STORAGE_CONFIG_PATH,
  try
    {ok, Fd} = file:open(StorageConfig, [append]),
    lists:foreach(fun(Path) -> file:write(Fd, "[[{name,cluster_fuse_id},{root,\"" ++ Path ++ "\"}]].\n") end, Paths),
    ok = file:close(Fd),
    ok
  catch
    _:_ -> error
  end.

%% add_storage_paths_on_hosts/2
%% ====================================================================
%% @doc Adds storage configuration on hosts
%% @end
-spec add_storage_paths_on_hosts(Hosts :: [string()], Paths :: [string()]) -> ok | {error, ErrorHosts :: [string()]}.
%% ====================================================================
add_storage_paths_on_hosts(Hosts, Paths) ->
  {HostsOk, HostsFailed} = install_utils:apply_on_hosts(Hosts, ?MODULE, add_storage_paths, [Paths], ?RPC_TIMEOUT),
  StoragePaths = case dao:get_record(configurations, last) of
                   #configuration{storage_paths = InstalledStoragePaths} -> InstalledStoragePaths;
                   _ -> []
                 end,
  case dao:update_record(configurations, #configuration{id = last, storage_paths = StoragePaths ++ Paths}) of
    ok ->
      case HostsFailed of
        [] -> ok;
        _ -> {error, HostsFailed}
      end;
    _ ->
      lager:error("Error while updating storage configuration."),
      rpc:multicall(HostsOk, ?MODULE, remove_storage_paths, [Paths], ?RPC_TIMEOUT),
      {error, Hosts}
  end.
