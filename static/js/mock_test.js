/* mock_test.js - runs the timed mock test in the browser.
   The browser only shows questions and sends selections.
   The server keeps the time limit and calculates the score. */
(function () {
  "use strict";

  var dataElement = document.getElementById("test-data");
  if (!dataElement) { return; }

  var data = JSON.parse(dataElement.textContent);
  var questions = data.questions;
  var answers = data.answers || {};            // question id -> "A".."D"
  var current = 0;
  var submitting = false;
  var endTime = Date.now() + data.remainingSeconds * 1000;
  var timerId = null;

  function byId(id) { return document.getElementById(id); }

  var el = {
    number: byId("q-number"), text: byId("q-text"), options: byId("q-options"),
    prev: byId("btn-prev"), next: byId("btn-next"), clear: byId("btn-clear"),
    palette: byId("palette"), answered: byId("answered-count"), status: byId("save-status"),
    timer: byId("timer"), timerText: byId("timer-text"),
    submitBtn: byId("btn-submit"), confirmBtn: byId("btn-confirm-submit"),
    modalSummary: byId("modal-summary"), modalEl: byId("confirmModal"),
    form: byId("submit-form"), answersInput: byId("answers-input")
  };

  // ---------------- Helpers ----------------
  function answeredCount() {
    return questions.filter(function (q) { return answers[q.id]; }).length;
  }

  function pad(n) { return n < 10 ? "0" + n : String(n); }

  function formatTime(totalSeconds) {
    var h = Math.floor(totalSeconds / 3600);
    var m = Math.floor((totalSeconds % 3600) / 60);
    var s = totalSeconds % 60;
    return (h > 0 ? h + ":" + pad(m) : pad(m)) + ":" + pad(s);
  }

  function setStatus(message, kind) {
    el.status.textContent = message;
    el.status.className = "small text-" + (kind || "muted");
  }

  // ---------------- Drawing the page ----------------
  function renderQuestion() {
    var q = questions[current];
    el.number.textContent = "Question " + (current + 1) + " of " + questions.length;
    el.text.textContent = q.text;
    el.options.innerHTML = "";

    ["A", "B", "C", "D"].forEach(function (letter) {
      var label = document.createElement("label");
      label.className = "option-item" + (answers[q.id] === letter ? " selected" : "");

      var input = document.createElement("input");
      input.type = "radio";
      input.name = "option";
      input.value = letter;
      input.checked = answers[q.id] === letter;
      input.addEventListener("change", function () { setAnswer(letter); });

      var badge = document.createElement("span");
      badge.className = "option-letter";
      badge.textContent = letter + ".";

      var text = document.createElement("span");
      text.textContent = q.options[letter];

      label.appendChild(input);
      label.appendChild(badge);
      label.appendChild(text);
      el.options.appendChild(label);
    });

    el.prev.disabled = current === 0;
    el.next.disabled = current === questions.length - 1;
    el.clear.disabled = !answers[q.id];
    renderPalette();
    el.answered.textContent = answeredCount();
  }

  function renderPalette() {
    el.palette.innerHTML = "";
    questions.forEach(function (q, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = index + 1;
      button.className = "btn btn-sm palette-btn" +
        (answers[q.id] ? " answered" : "") + (index === current ? " current" : "");
      button.setAttribute("aria-label", "Go to question " + (index + 1) +
        (answers[q.id] ? " (answered)" : " (not answered)"));
      button.addEventListener("click", function () { goTo(index); });
      el.palette.appendChild(button);
    });
  }

  function goTo(index) {
    if (index < 0 || index >= questions.length) { return; }
    current = index;
    renderQuestion();
  }

  // ---------------- Answers ----------------
  function setAnswer(letter) {
    var q = questions[current];
    if (letter) { answers[q.id] = letter; } else { delete answers[q.id]; }
    renderQuestion();
    saveToServer(q.id, letter);
  }

  function saveToServer(questionId, letter) {
    setStatus("Saving...", "muted");
    fetch(data.saveUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": window.getCsrfToken() },
      body: JSON.stringify({ question_id: questionId, option: letter || null })
    }).then(function (response) {
      if (response.redirected) { throw new Error("redirected"); }
      if (response.status === 409) {
        return response.json().then(function (body) {
          if (body.error === "time_up") { submitTest(true); }
          else { window.location.reload(); }   // already submitted elsewhere
        });
      }
      if (!response.ok) { throw new Error("HTTP " + response.status); }
      setStatus("Saved", "success");
    }).catch(function () {
      setStatus("Not saved yet. It will be sent when you submit.", "warning");
    });
  }

  // ---------------- Timer ----------------
  function tick() {
    var left = Math.max(0, Math.round((endTime - Date.now()) / 1000));
    el.timerText.textContent = formatTime(left);
    el.timer.classList.toggle("timer-warning", left <= 60);
    if (left <= 0 && !submitting) {
      clearInterval(timerId);
      submitTest(true);
    }
  }

  // ---------------- Submitting ----------------
  function submitTest(automatic) {
    if (submitting) { return; }
    submitting = true;
    setStatus(automatic ? "Time is up! Submitting your test..." : "Submitting your test...", "danger");
    [el.prev, el.next, el.clear, el.submitBtn, el.confirmBtn].forEach(function (b) { b.disabled = true; });
    el.answersInput.value = JSON.stringify(answers);   // sends every selection, so nothing is lost
    el.form.submit();
  }

  el.submitBtn.addEventListener("click", function () {
    var unanswered = questions.length - answeredCount();
    el.modalSummary.textContent = unanswered > 0
      ? "You have answered " + answeredCount() + " of " + questions.length + " questions. " +
        unanswered + " unanswered question" + (unanswered === 1 ? " will" : "s will") + " score zero."
      : "You have answered all " + questions.length + " questions.";
    window.bootstrap.Modal.getOrCreateInstance(el.modalEl).show();
  });
  el.confirmBtn.addEventListener("click", function () { submitTest(false); });

  el.prev.addEventListener("click", function () { goTo(current - 1); });
  el.next.addEventListener("click", function () { goTo(current + 1); });
  el.clear.addEventListener("click", function () { setAnswer(null); });

  // Warn before leaving by accident. Answers are saved, but the timer keeps running.
  window.addEventListener("beforeunload", function (event) {
    if (!submitting) { event.preventDefault(); event.returnValue = ""; }
  });

  // ---------------- Start ----------------
  renderQuestion();
  tick();
  timerId = setInterval(tick, 250);
})();