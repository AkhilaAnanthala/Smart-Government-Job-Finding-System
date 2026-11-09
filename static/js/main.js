/* main.js - small helpers used on every page */
(function () {
  "use strict";

  // CSRF token for AJAX (fetch) requests. Used by mock_test.js in Part 8.
  window.getCsrfToken = function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  };

  // 1. Success / info messages close automatically after 6 seconds
  document.querySelectorAll(".alert.auto-dismiss").forEach(function (alertBox) {
    setTimeout(function () {
      if (window.bootstrap && document.body.contains(alertBox)) {
        window.bootstrap.Alert.getOrCreateInstance(alertBox).close();
      }
    }, 6000);
  });

  // 2. Show / hide password:  <button data-toggle-password="#password">
  document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.querySelector(button.getAttribute("data-toggle-password"));
      if (!input) { return; }
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      var icon = button.querySelector("i");
      if (icon) { icon.className = show ? "bi bi-eye-slash" : "bi bi-eye"; }
    });
  });

  // 3. Forms: optional confirmation + loading spinner on the submit button
  //    <form data-confirm="Delete this job?">     asks before submitting
  //    <form data-no-loading> or <button data-no-loading>   skips the spinner
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) { return; }

    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
      return;
    }

    var button = event.submitter || form.querySelector('button[type="submit"]');
    if (!button || form.hasAttribute("data-no-loading") || button.hasAttribute("data-no-loading")) {
      return;
    }

    // Disable after the browser has collected the form data.
    setTimeout(function () {
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.innerHTML =
        '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Please wait...';
    }, 0);
  });

  // If the user presses the browser Back button, restore any disabled buttons.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) { return; }
    document.querySelectorAll("button[data-original-html]").forEach(function (button) {
      button.innerHTML = button.dataset.originalHtml;
      button.disabled = false;
    });
  });
})();