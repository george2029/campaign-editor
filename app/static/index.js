const form = document.getElementById("create-form");
const result = document.getElementById("create-result");
const offerChosen = document.getElementById("offer-chosen");
let chosenOffer = null;

offerPicker(document.getElementById("offer-search"), (offer) => {
  chosenOffer = offer;
  document.getElementById("offer-search").value = "";
  offerChosen.textContent = `${offer.id} ${offer.name}`;
  offerChosen.classList.add("chosen");
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!chosenOffer) {
    result.innerHTML = `<p class="error">Choose an offer first</p>`;
    return;
  }
  const button = form.querySelector("button");
  button.disabled = true;
  result.innerHTML = "";
  try {
    const campaign = await api("POST", "/api/campaigns", {
      // form.elements.name, not form.name: that one is the form's own name attribute
      name: form.elements.name.value,
      geo: form.elements.geo.value.split(/[\s,]+/).filter(Boolean),
      offer_id: chosenOffer.id,
    });
    result.innerHTML =
      `<p class="success">Campaign <b>${escapeHtml(campaign.name)}</b> created: ` +
      `<code>${escapeHtml(campaign.url)}</code> · <a href="/campaigns/${campaign.id}">Edit offers</a></p>`;
    form.reset();
    chosenOffer = null;
    offerChosen.textContent = "No offer chosen";
    offerChosen.classList.remove("chosen");
    loadCampaigns();
  } catch (error) {
    result.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
  }
});

async function loadCampaigns() {
  const tbody = document.getElementById("campaigns");
  try {
    const campaigns = await api("GET", "/api/campaigns");
    if (campaigns.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted">No campaigns yet</td></tr>`;
      return;
    }
    tbody.innerHTML = campaigns
      .map(
        (c) => `<tr>
          <td>${c.id}</td>
          <td>${escapeHtml(c.name)} ${c.created_here ? `<span class="badge">created here</span>` : ""}</td>
          <td><code>${escapeHtml(c.url)}</code></td>
          <td>${escapeHtml(c.group || "")}</td>
          <td class="muted">${c.created_at}</td>
          <td><a href="/campaigns/${c.id}">Edit</a></td>
        </tr>`,
      )
      .join("");
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="6" class="error">${escapeHtml(error.message)}</td></tr>`;
  }
}

loadCampaigns();
loadOffers();
