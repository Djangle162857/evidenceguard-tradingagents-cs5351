from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from test_integration_context import context  # noqa: F401

from evidenceguard.integration import IntegrationContext


def test_wrap_tools_frozen_actual_input_schemas(context: IntegrationContext) -> None:  # noqa: F811
    context, eid = context

    def _boom(*_args, **_kwargs):
        raise AssertionError("underlying frozen tool must not execute")

    @tool
    def get_stock_data(symbol: str) -> str:
        """Return frozen market data for a symbol."""
        return _boom()

    @tool
    def get_news(symbol: str) -> str:
        """Return frozen news items for a symbol."""
        return _boom()

    @tool
    def forbidden(symbol: str) -> str:
        """A tool that is not registered as eligible."""
        return _boom()

    wrapped = context.wrap_tools([get_stock_data, get_news, forbidden])
    assert [t.name for t in wrapped] == ["get_stock_data", "get_news"]

    market = wrapped[0].invoke({"symbol": "AAPL"})
    assert isinstance(market, str)
    assert eid in market

    news = wrapped[1].invoke({"symbol": "AAPL"})
    assert isinstance(news, str)
    assert "No eligible evidence in snapshot." in news


def test_tool_message_chain_survives_compaction(context: IntegrationContext) -> None:  # noqa: F811
    context, eid = context
    ai = AIMessage(
        content="long tool statement",
        tool_calls=[{"id": "call1", "name": "get_stock_data", "args": {"symbol": "AAPL"}}],
    )
    tool_msg = ToolMessage(content="frozen result", tool_call_id="call1", name="get_stock_data")
    upstream_system = SystemMessage(content="catalog" * 2000)
    messages = [upstream_system, ai, tool_msg, HumanMessage(content="now report")]

    spy = context.wrap(RunnableLambda(lambda x: x), "market")
    result = spy.invoke(messages)

    systems = [m for m in result if isinstance(m, SystemMessage)]
    assert len(systems) == 1

    ai_out = [m for m in result if isinstance(m, AIMessage)]
    assert len(ai_out) == 1
    assert ai_out[0].content == "long tool statement"
    assert ai_out[0].tool_calls == ai.tool_calls

    tool_out = [m for m in result if isinstance(m, ToolMessage)]
    assert len(tool_out) == 1
    assert tool_out[0].tool_call_id == "call1"
    assert tool_out[0].content == "frozen result"

    for m in result:
        if isinstance(m, SystemMessage):
            assert "catalog" not in (m.content or "")

    ordinary = [m for m in result if not (isinstance(m, (SystemMessage, AIMessage, ToolMessage)))]
    total = sum(len((m.content or "").encode("utf-8")) for m in ordinary)
    assert total <= 1200


def test_authoritative_time_uses_actual_as_of_utc(context: IntegrationContext) -> None:  # noqa: F811
    context, eid = context
    spy = context.wrap(RunnableLambda(lambda x: x), "trader")
    result = spy.invoke("hello")

    systems = [m for m in result if isinstance(m, SystemMessage)]
    assert systems, "prompt must contain at least one SystemMessage"
    first = systems[0].content or ""

    as_of_utc = context.manifest.to_dict()["as_of_utc"]
    assert as_of_utc in first

    assert eid in first

    huge = "中" * 4000
    result2 = spy.invoke(huge)
    huge.encode("utf-8").decode("utf-8")

    ordinary = [m for m in result2 if not (isinstance(m, (SystemMessage, AIMessage, ToolMessage)))]
    total = sum(len((m.content or "").encode("utf-8")) for m in ordinary)
    assert total <= 1200
