// Campaign editor: shows the flows of one campaign and lets you change the
// offers of a flow. Changes are a local draft until "Push to KT".

const campaignId = Number(location.pathname.split("/").pop());
const streamsBox = document.getElementById("streams");
const pageError = document.getElementById("page-error");

let streams = [];
let offerNames = {}; // offer id -> offer from /api/offers
// One draft per offers flow:
// {
//   original: [{offer_id, share}]   what is in Keitaro now
//   start: [...]                    what the editor starts from: offers in Keitaro + removed ones (from our DB)
//   offers: [{offer_id, share, pinned, removed}]   the draft being edited
//   lastShare: {offer_id: share}    share a removed offer had before it was pushed out
//   error
// }
let drafts = {};

// Offers in the flow, then offers pushed out earlier, greyed out with "Bring back".
function startingOffers(stream) {
  return [
    ...stream.offers.map((o) => ({ ...o, pinned: false, removed: false })),
    ...stream.removed_offers.map((o) => ({
      offer_id: o.offer_id,
      share: 0,
      pinned: false,
      removed: true,
    })),
  ];
}

async function fetchCampaign() {
  pageError.hidden = true;
  try {
    const [campaign, offers] = await Promise.all([
      api("GET", `/api/campaigns/${campaignId}`),
      loadOffers(),
    ]);
    offers.forEach((o) => (offerNames[o.id] = o));
    document.getElementById("campaign-name").textContent = campaign.name;
    document.getElementById("campaign-url").textContent = campaign.url;
    document.title = `${campaign.name} · Campaign editor`;
    streams = campaign.streams;
    drafts = {};
    for (const s of streams) {
      if (isOffersStream(s)) {
        const start = startingOffers(s);
        const lastShare = {};
        s.removed_offers.forEach((o) => (lastShare[o.offer_id] = o.last_share));
        drafts[s.id] = {
          original: s.offers,
          start,
          offers: start.map((o) => ({ ...o })),
          lastShare,
          error: "",
        };
      }
    }
    render();
  } catch (error) {
    pageError.textContent = error.message;
    pageError.hidden = false;
  }
  loadChanges();
}

function isOffersStream(stream) {
  return stream.schema === "landings" || stream.offers.length > 0;
}

// A draft is changed when the offers that stay in the flow, or their shares, differ.
function isChanged(draft) {
  const now = draft.offers
    .filter((o) => !o.removed)
    .map((o) => `${o.offer_id}:${o.share}`);
  const before = draft.original.map((o) => `${o.offer_id}:${o.share}`);
  return now.sort().join() !== before.sort().join();
}

function offerLabel(offerId) {
  const offer = offerNames[offerId];
  if (!offer) return `${offerId} <span class="muted">unknown offer</span>`;
  // Offer names already start with the offer id ("18001 Detoxin ...")
  return `${escapeHtml(offer.name)}<span class="country">${offer.country.join(", ")}</span>`;
}

function filtersText(filters) {
  return filters
    .map(
      (f) =>
        `${f.name} ${f.mode === "accept" ? "is" : "is not"} ${f.payload.join(", ")}`,
    )
    .join("; ");
}

function render() {
  streamsBox.innerHTML = streams
    .map((s) =>
      isOffersStream(s) ? renderOffersStream(s) : renderRedirectStream(s),
    )
    .join("");
  for (const s of streams) {
    if (isOffersStream(s)) {
      offerPicker(document.getElementById(`add-${s.id}`), (offer) =>
        addOffer(s.id, offer),
      );
    }
  }
}

function renderRedirectStream(s) {
  return `<section class="card stream">
    <h2>Flow ${s.position}: ${escapeHtml(s.name)}</h2>
    <p>${s.filters.length ? `If ${escapeHtml(filtersText(s.filters))}` : "Everyone"}
      → redirect to <code>${escapeHtml(s.action_payload || "")}</code></p>
  </section>`;
}

function renderOffersStream(s) {
  const draft = drafts[s.id];
  const changed = isChanged(draft);
  const total = draft.offers
    .filter((o) => !o.removed)
    .reduce((sum, o) => sum + o.share, 0);

  const rows = draft.offers
    .map((o, i) => {
      const data = `data-stream="${s.id}" data-index="${i}"`;
      if (o.removed) {
        const was = draft.lastShare[o.offer_id];
        return `<tr class="removed">
          <td>${offerLabel(o.offer_id)} <span class="badge">removed</span></td>
          <td class="share">0% ${was !== undefined ? `<span class="was">was ${was}%</span>` : ""}</td>
          <td class="actions"><button data-action="bring-back" ${data}>Bring back</button></td>
        </tr>`;
      }
      return `<tr class="${o.pinned ? "pinned" : ""}">
        <td>${offerLabel(o.offer_id)}</td>
        <td class="share">
          <input type="number" min="0" max="100" value="${o.share}" data-action="share" ${data} />%
          <button class="pin ${o.pinned ? "on" : ""}" data-action="pin" ${data}
            title="${o.pinned ? "Pinned: keeps its share. Click to unpin" : "Pin this share"}">📌</button>
        </td>
        <td class="actions"><button data-action="remove" ${data}>Remove</button></td>
      </tr>`;
    })
    .join("");

  return `<section class="card stream ${changed ? "changed" : ""}">
    <h2>Flow ${s.position}: ${escapeHtml(s.name)}</h2>
    ${s.filters.length ? `<p class="muted">If ${escapeHtml(filtersText(s.filters))}</p>` : ""}
    ${
      changed
        ? `<div class="draft-bar">
            <span>Unsaved changes</span>
            <button class="primary" data-action="push" data-stream="${s.id}">Push to KT</button>
            <button data-action="cancel" data-stream="${s.id}">Cancel</button>
          </div>`
        : ""
    }
    ${draft.error ? `<p class="error">${escapeHtml(draft.error)}</p>` : ""}
    <table>
      <thead><tr><th>Offer</th><th>Share</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td>Total</td><td class="share ${total === 100 ? "" : "error"}">${total}%</td><td></td></tr></tfoot>
    </table>
    <div class="picker add-offer">
      <input id="add-${s.id}" placeholder="+ add offer: search by id, name or country" autocomplete="off" />
    </div>
  </section>`;
}

// Send the changed list to the server, which recalculates the shares.
// If the change is impossible (e.g. pinned offers over 100%), keep the old list.
async function applyChange(streamId, offers) {
  const draft = drafts[streamId];
  try {
    draft.offers = await api("POST", "/api/rebalance", offers);
    draft.error = "";
  } catch (error) {
    draft.error = error.message;
  }
  render();
}

function copyOffers(streamId) {
  return drafts[streamId].offers.map((o) => ({ ...o }));
}

function addOffer(streamId, offer) {
  const offers = copyOffers(streamId);
  const existing = offers.find((o) => o.offer_id === offer.id);
  if (existing && !existing.removed) {
    drafts[streamId].error = `Offer ${offer.id} is already in this flow`;
    render();
    return;
  }
  if (existing) {
    existing.removed = false;
    existing.pinned = false;
  } else {
    offers.push({
      offer_id: offer.id,
      share: 0,
      pinned: false,
      removed: false,
    });
  }
  applyChange(streamId, offers);
}

async function push(streamId) {
  const draft = drafts[streamId];
  try {
    await api("PUT", `/api/streams/${streamId}/offers`, {
      campaign_id: campaignId,
      offers: draft.offers,
    });
    await fetchCampaign();
  } catch (error) {
    draft.error = error.message;
    render();
  }
}

streamsBox.addEventListener("click", (e) => {
  const button = e.target.closest("button[data-action]");
  if (!button) return;
  const streamId = Number(button.dataset.stream);
  const index = Number(button.dataset.index);
  const offers = copyOffers(streamId);

  switch (button.dataset.action) {
    case "pin":
      offers[index].pinned = !offers[index].pinned;
      applyChange(streamId, offers);
      break;
    case "remove":
      offers[index].removed = true;
      applyChange(streamId, offers);
      break;
    case "bring-back":
      offers[index].removed = false;
      offers[index].pinned = false;
      applyChange(streamId, offers);
      break;
    case "cancel":
      drafts[streamId].offers = drafts[streamId].start.map((o) => ({ ...o }));
      drafts[streamId].error = "";
      render();
      break;
    case "push":
      button.disabled = true;
      push(streamId);
      break;
  }
});

// Typing a share pins that offer; the others share what is left.
streamsBox.addEventListener("change", (e) => {
  const input = e.target;
  if (input.dataset.action !== "share") return;
  const streamId = Number(input.dataset.stream);
  const offers = copyOffers(streamId);
  offers[Number(input.dataset.index)].share = Math.round(
    Number(input.value) || 0,
  );
  offers[Number(input.dataset.index)].pinned = true;
  applyChange(streamId, offers);
});

async function loadChanges() {
  const box = document.getElementById("changes");
  const changes = await api("GET", `/api/campaigns/${campaignId}/changes`);
  if (changes.length === 0) {
    box.textContent = "Nothing pushed yet";
    return;
  }
  const list = (offers) =>
    offers.map((o) => `${o.offer_id}: ${o.share}%`).join(", ") || "—";
  box.classList.remove("muted");
  box.innerHTML = `<table>
    <thead><tr><th>When</th><th>Flow</th><th>Before</th><th>After</th></tr></thead>
    <tbody>${changes
      .map(
        (c) => `<tr>
          <td class="muted">${c.created_at.replace("T", " ").slice(0, 19)}</td>
          <td>${c.stream_id}</td>
          <td>${list(c.before)}</td>
          <td>${list(c.after)}</td>
        </tr>`,
      )
      .join("")}</tbody>
  </table>`;
}

document.getElementById("fetch").addEventListener("click", fetchCampaign);
fetchCampaign();
