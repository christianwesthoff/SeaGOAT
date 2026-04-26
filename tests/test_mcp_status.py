from seagoat.mcp_tools.status import run_server_status_tool


def test_run_server_status_tool_reports_running_server(tmp_path, mocker):
    mocker.patch(
        "seagoat.mcp_tools.status.get_server_info",
        return_value={
            "host": "127.0.0.1",
            "port": 31134,
            "address": "http://127.0.0.1:31134",
            "pid": 123,
        },
    )
    mocker.patch("seagoat.mcp_tools.status.is_server_running", return_value=True)

    result = run_server_status_tool(repo_path=str(tmp_path))

    assert result == {
        "summary": f"SeaGOAT server is running for '{tmp_path}'.",
        "repo_path": str(tmp_path),
        "running": True,
        "server_address": "http://127.0.0.1:31134",
        "start_command": f"seagoat-server start {tmp_path}",
    }


def test_run_server_status_tool_reports_missing_server(tmp_path, mocker):
    mocker.patch("seagoat.mcp_tools.status.is_server_running", return_value=False)
    mocked_get_server_info = mocker.patch("seagoat.mcp_tools.status.get_server_info")

    result = run_server_status_tool(repo_path=str(tmp_path))

    mocked_get_server_info.assert_not_called()
    assert result == {
        "summary": f"No SeaGOAT server is running for '{tmp_path}'.",
        "repo_path": str(tmp_path),
        "running": False,
        "server_address": None,
        "start_command": f"seagoat-server start {tmp_path}",
    }
