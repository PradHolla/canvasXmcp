from src.agent.bedrock_agent import BedrockAgent


def test_agent_respond():
    a = BedrockAgent(name="test")
    resp = a.respond("hello")
    assert "received" in resp


def test_agent_empty_prompt():
    a = BedrockAgent()
    try:
        a.respond("")
        assert False, "Expected ValueError for empty prompt"
    except ValueError:
        assert True
