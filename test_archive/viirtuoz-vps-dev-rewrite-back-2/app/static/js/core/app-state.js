"use strict";

/**
 * Lightweight shared app store for cross-page UI synchronization.
 * Keeps balances/profile in one place and notifies subscribers on changes.
 */
(function initAppState(global) {
  if (global.AppState) return;

  var state = {
    balances: {
      mainBalance: null,
      llmBalance: null,
      updatedAt: null,
    },
    profile: {
      username: document.body ? document.body.dataset.username || "" : "",
      namespace: "",
    },
    vmSummary: {
      total: null,
      running: null,
      updatedAt: null,
    },
  };

  var listeners = [];

  function notify(source) {
    for (var i = 0; i < listeners.length; i += 1) {
      try {
        listeners[i](state, source || "unknown");
      } catch (_) {}
    }
    try {
      global.dispatchEvent(
        new CustomEvent("appstate:change", {
          detail: {
            source: source || "unknown",
            state: state,
          },
        }),
      );
    } catch (_) {}
  }

  function subscribe(listener) {
    if (typeof listener !== "function") return function noop() {};
    listeners.push(listener);
    return function unsubscribe() {
      listeners = listeners.filter(function (cb) {
        return cb !== listener;
      });
    };
  }

  function setState(nextPartial, source) {
    if (!nextPartial || typeof nextPartial !== "object") return;
    if (nextPartial.balances) {
      state.balances = Object.assign({}, state.balances, nextPartial.balances);
    }
    if (nextPartial.profile) {
      state.profile = Object.assign({}, state.profile, nextPartial.profile);
    }
    if (nextPartial.vmSummary) {
      state.vmSummary = Object.assign({}, state.vmSummary, nextPartial.vmSummary);
    }
    notify(source || "setState");
  }

  function setBalances(rawBalances, source) {
    if (!rawBalances || typeof rawBalances !== "object") return;
    var mainVal = Number(rawBalances.main_balance);
    var llmVal = Number(rawBalances.llm_balance);
    setState(
      {
        balances: {
          mainBalance: Number.isFinite(mainVal) ? mainVal : null,
          llmBalance: Number.isFinite(llmVal) ? llmVal : null,
          updatedAt: Date.now(),
        },
      },
      source || "setBalances",
    );
  }

  function formatMoney(value) {
    var num = Number(value);
    return Number.isFinite(num) ? num.toFixed(2) : "—";
  }

  function loadBalances(username) {
    var user = username || state.profile.username;
    if (!user) return Promise.resolve(null);
    return fetch("/" + encodeURIComponent(user) + "/api/balance", {
      credentials: "same-origin",
    })
      .then(function (r) {
        if (r.status === 401) {
          global.location.href = "/login";
          return null;
        }
        if (!r.ok) return Promise.reject(new Error("Failed to load balances"));
        return r.json();
      })
      .then(function (data) {
        if (!data) return null;
        setBalances(data, "loadBalances");
        return data;
      });
  }

  global.AppState = {
    getState: function getState() {
      return JSON.parse(JSON.stringify(state));
    },
    subscribe: subscribe,
    setState: setState,
    setBalances: setBalances,
    loadBalances: loadBalances,
    formatMoney: formatMoney,
  };
})(window);
