// Helpers shared by both pages.

async function api(method, url, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(errorText(data.detail));
  }
  return data;
}

// FastAPI errors are either a string or a list of validation errors.
function errorText(detail) {
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg.replace(/^Value error, /, "")).join("; ");
  }
  return detail || "Something went wrong";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// All offers, loaded once per page.
let offersPromise = null;
function loadOffers() {
  if (!offersPromise) {
    offersPromise = api("GET", "/api/offers");
  }
  return offersPromise;
}

// Search box with a dropdown of matching offers.
// Search by id, name or country; calls onPick(offer) when one is chosen.
function offerPicker(input, onPick) {
  const list = document.createElement("ul");
  list.className = "picker-list";
  list.hidden = true;
  input.after(list);

  let matches = [];
  let active = 0;

  function render() {
    list.innerHTML = matches
      .map(
        (o, i) =>
          // Offer names already start with the offer id ("18001 Detoxin ...")
          `<li data-i="${i}" class="${i === active ? "active" : ""}">${escapeHtml(o.name)}` +
          `<span class="country">${o.country.join(", ")}</span></li>`,
      )
      .join("");
    list.hidden = matches.length === 0;
  }

  async function search() {
    const query = input.value.trim().toLowerCase();
    if (!query) {
      matches = [];
      render();
      return;
    }
    const offers = await loadOffers();
    matches = offers
      .filter(
        (o) =>
          String(o.id).includes(query) ||
          o.name.toLowerCase().includes(query) ||
          o.country.some((c) => c.toLowerCase() === query),
      )
      .slice(0, 15);
    active = 0;
    render();
  }

  function pick(offer) {
    matches = [];
    render();
    onPick(offer);
  }

  input.addEventListener("input", search);
  input.addEventListener("focus", search);
  input.addEventListener("blur", () =>
    setTimeout(() => (list.hidden = true), 150),
  );
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown")
      active = Math.min(active + 1, matches.length - 1);
    else if (e.key === "ArrowUp") active = Math.max(active - 1, 0);
    else if (e.key === "Enter") pick(matches[active]);
    else if (e.key === "Escape") matches = [];
    else return;
    e.preventDefault();
    render();
  });
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li");
    if (li) pick(matches[li.dataset.i]);
  });
}
