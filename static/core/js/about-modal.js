/* ============================================================
   About Modal — opens on Ctrl/Cmd+Shift+A or the Konami code
   ============================================================ */
(function () {
  "use strict";

  const modal    = document.getElementById("aboutModal");
  if (!modal) return;                       // graceful exit if not present

  const dialog   = modal.querySelector(".about-modal");
  const closeBtn = modal.querySelector(".about-modal-close");

  let lastFocused = null;

  /* ---------- open / close ---------- */
  function isOpen() { return modal.classList.contains("is-open"); }

  function openModal() {
    if (isOpen()) return;
    lastFocused = document.activeElement;
    modal.classList.add("is-open");
    document.body.style.overflow = "hidden";   // scroll lock
    closeBtn.focus();
  }

  function closeModal() {
    if (!isOpen()) return;
    modal.classList.remove("is-open");
    document.body.style.overflow = "";
    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
  }

  /* ---------- primary shortcut: Ctrl/Cmd + Shift + A ---------- */
  document.addEventListener("keydown", function (e) {
    const modifier = e.ctrlKey || e.metaKey;

    if (modifier && e.shiftKey && e.code === "KeyA") {
      e.preventDefault();
      isOpen() ? closeModal() : openModal();
      return;
    }

    if (e.key === "Escape" && isOpen()) {
      e.preventDefault();
      closeModal();
    }
  });

  /* ---------- close interactions ---------- */
  closeBtn.addEventListener("click", closeModal);

  modal.addEventListener("mousedown", function (e) {
    if (e.target === modal) closeModal();      // click on backdrop
  });

  /* ---------- focus trap ---------- */
  modal.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;

    const focusables = dialog.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), ' +
      'select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusables.length) return;

    const first = focusables[0];
    const last  = focusables[focusables.length - 1];

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  });

  /* ---------- easter egg: Konami code ---------- */
  const KONAMI = ["ArrowUp","ArrowUp","ArrowDown","ArrowDown",
                  "ArrowLeft","ArrowRight","ArrowLeft","ArrowRight",
                  "KeyB","KeyA"];
  let progress = 0;

  document.addEventListener("keydown", function (e) {
    progress = (e.code === KONAMI[progress]) ? progress + 1 : 0;
    if (progress === KONAMI.length) {
      progress = 0;
      openModal();
    }
  });

  /* ---------- public API (optional) ---------- */
  window.AboutModal = { open: openModal, close: closeModal, toggle: isOpen };
})();