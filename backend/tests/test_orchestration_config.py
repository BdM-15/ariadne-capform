from thread.config import Settings


def test_langgraph_studio_port_defaults_to_thread_family():
    s = Settings()
    assert s.langgraph_studio_port == 9623
    assert s.langgraph_studio_base_url == "http://127.0.0.1:9623"


def test_theseus_studio_alias_accepted():
    s = Settings(theseus_langgraph_studio_auto_start=True)
    assert s.thread_langgraph_studio_auto_start is True


def test_langchain_api_key_falls_back_to_langsmith():
    s = Settings(langsmith_api_key="ls-test", langchain_api_key=None)
    assert s.resolved_langchain_api_key == "ls-test"


def test_langchain_project_falls_back_to_langsmith_project():
    s = Settings(langsmith_project="thread-capture-orchestration", langchain_project=None)
    assert s.resolved_langchain_project == "thread-capture-orchestration"