(function () {
  "use strict";
  var SYMBOLS = ["AAPL", "MSFT", "NVDA"];
  var STYLES = [0, 1, 2, 3, 8, 9];
  var INTERVALS = ["1", "5", "15", "30", "60", "120", "D", "W", "M"];
  var RANGE_INTERVAL = {
    "1D": "1", "5D": "5", "1M": "30", "3M": "60",
    "6M": "120", "12M": "D", "60M": "W", "ALL": "M"
  };
  var BASE = "https://www.tradingview-widget.com/embed-widget/advanced-chart/?locale=zh_CN#";

  var state = {
    symbol: "AAPL",
    style: 1,
    interval: "60",
    range: "3M",
    online: true
  };

  function pick(list, value, fallback) {
    for (var i = 0; i < list.length; i += 1) {
      if (String(list[i]) === String(value)) { return list[i]; }
    }
    return fallback;
  }

  function init() {
    var symbolEl = document.getElementById("market-symbol");
    var styleEl = document.getElementById("chart-type");
    var intervalEl = document.getElementById("chart-interval");
    var host = document.getElementById("live-chart-host");
    var statusEl = document.getElementById("chart-status");
    var tickerEl = document.getElementById("market-ticker");
    var markEl = document.querySelector(".stock-mark");
    var reloadEl = document.getElementById("reload-chart");
    var toggleEl = document.getElementById("toggle-chart");
    var rangeButtons = Array.prototype.slice.call(document.querySelectorAll("button[data-range]"));

    if (!host) { return; }

    var frame = null;

    function render() {
      if (symbolEl) { symbolEl.value = String(state.symbol); }
      if (styleEl) { styleEl.value = String(state.style); }
      if (intervalEl) { intervalEl.value = String(state.interval); }
      if (tickerEl) { tickerEl.textContent = state.symbol; }
      if (markEl) { markEl.textContent = state.symbol.charAt(0); }
      if (toggleEl) { toggleEl.textContent = state.online ? "关闭在线行情" : "加载在线行情"; }

      rangeButtons.forEach(function (btn) {
        var active = btn.getAttribute("data-range") === state.range;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
        btn.classList.remove("is-selected");
      });

      host.replaceChildren();
      frame = null;

      if (!state.online) {
        if (statusEl) { statusEl.textContent = "已关闭"; }
        host.textContent = "在线行情已关闭；报告仍可本地查看。";
        return;
      }

      if (statusEl) { statusEl.textContent = "正在连接行情源…"; }

      var settings = {
        symbol: "NASDAQ:" + state.symbol,
        style: state.style,
        interval: state.interval,
        timezone: "Asia/Hong_Kong",
        theme: "dark",
        autosize: true,
        allow_symbol_change: false,
        withdateranges: true,
        hide_side_toolbar: false,
        hide_top_toolbar: false,
        hide_volume: false,
        save_image: false,
        enable_publishing: false
      };
      if (state.range !== null) { settings.range = state.range; }

      frame = document.createElement("iframe");
      frame.src = BASE + encodeURIComponent(JSON.stringify(settings));
      frame.title = state.symbol + "真实行情图表";
      frame.referrerPolicy = "no-referrer";
      frame.setAttribute("sandbox", "allow-scripts allow-same-origin");
      frame.allowFullscreen = true;
      frame.addEventListener("load", function () {
        if (statusEl) { statusEl.textContent = "TradingView行情 · 可能延迟"; }
      });
      frame.addEventListener("error", function () {
        if (statusEl) { statusEl.textContent = "行情加载失败，请重试"; }
      });
      host.appendChild(frame);
    }

    if (symbolEl) {
      symbolEl.addEventListener("change", function () {
        state.symbol = pick(SYMBOLS, symbolEl.value, "AAPL");
        render();
      });
    }

    if (styleEl) {
      styleEl.addEventListener("change", function () {
        state.style = Number(pick(STYLES, styleEl.value, 1));
        render();
      });
    }

    if (intervalEl) {
      intervalEl.addEventListener("change", function () {
        state.interval = pick(INTERVALS, intervalEl.value, "D");
        state.range = null;
        render();
      });
    }

    rangeButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var range = btn.getAttribute("data-range");
        if (!Object.prototype.hasOwnProperty.call(RANGE_INTERVAL, range)) { return; }
        state.range = range;
        state.interval = RANGE_INTERVAL[range];
        render();
      });
    });

    if (reloadEl) {
      reloadEl.addEventListener("click", function () {
        state.online = true;
        render();
      });
    }

    if (toggleEl) {
      toggleEl.addEventListener("click", function () {
        state.online = !state.online;
        render();
      });
    }

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
