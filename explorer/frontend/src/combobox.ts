// A small typeahead combobox: filters a username list as you type (client-side, substring match),
// shows game counts, supports keyboard navigation, and clears with a button. Selecting a value
// fires `onChange`; mere typing does not, so we never hit the API on every keystroke.

import { UserOption } from "./db";

const MAX_RESULTS = 20;

export interface ComboboxController {
  set(value: string): void; // programmatically commit a value (e.g. from the games panel)
}

export function setupCombobox(
  root: HTMLElement,
  options: UserOption[],
  onChange: (value: string) => void
): ComboboxController {
  const input = root.querySelector<HTMLInputElement>(".combobox-input")!;
  const clear = root.querySelector<HTMLButtonElement>(".combobox-clear")!;
  const menu = root.querySelector<HTMLUListElement>(".combobox-menu")!;

  let committed = "";
  let matches: UserOption[] = [];
  let highlight = -1;

  function closeMenu() {
    menu.hidden = true;
    highlight = -1;
  }

  function commit(value: string) {
    committed = value;
    input.value = value;
    clear.hidden = value === "";
    closeMenu();
    onChange(value);
  }

  function openMenu() {
    const q = input.value.trim().toLowerCase();
    matches = (q ? options.filter((o) => o.name.toLowerCase().includes(q)) : options).slice(
      0,
      MAX_RESULTS
    );
    menu.innerHTML = "";
    matches.forEach((o, i) => {
      const li = document.createElement("li");
      li.className = "combobox-item" + (i === highlight ? " active" : "");
      li.innerHTML = `<span class="cb-name"></span><span class="cb-count">${o.count.toLocaleString()}</span>`;
      li.querySelector(".cb-name")!.textContent = o.name; // textContent avoids HTML injection
      li.addEventListener("mousedown", (e) => {
        e.preventDefault(); // keep focus so blur-revert doesn't fire first
        commit(o.name);
      });
      menu.appendChild(li);
    });
    menu.hidden = matches.length === 0;
  }

  function paint() {
    [...menu.children].forEach((li, i) => li.classList.toggle("active", i === highlight));
  }

  input.addEventListener("input", () => {
    highlight = -1;
    openMenu();
  });
  input.addEventListener("focus", openMenu);
  input.addEventListener("keydown", (e) => {
    if (menu.hidden) return;
    if (e.key === "ArrowDown") {
      highlight = Math.min(highlight + 1, matches.length - 1);
      paint();
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      highlight = Math.max(highlight - 1, 0);
      paint();
      e.preventDefault();
    } else if (e.key === "Enter" && highlight >= 0) {
      commit(matches[highlight].name);
      e.preventDefault();
    } else if (e.key === "Escape") {
      closeMenu();
    }
  });
  input.addEventListener("blur", () => {
    // Revert any uncommitted typing after a click on a menu item has had a chance to fire.
    setTimeout(() => {
      input.value = committed;
      closeMenu();
    }, 120);
  });
  clear.addEventListener("click", () => commit(""));

  return { set: commit };
}
