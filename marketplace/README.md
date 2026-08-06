# Logic Flow Systems Marketplace

**Deploy to Netlify:**
1. Go to https://app.netlify.com/drop
2. Drag this entire `marketplace/` folder onto the page
3. Get a live URL like `xyz.netlify.app`
4. Optionally: point `intel.logicflowsystems.io` DNS at Netlify

**Local test:**
Open `index.html` in your browser. All tiles work as `mailto:` orders.

**Fulfillment workflow:**
1. Buyer clicks tile → email opens with order details
2. You receive email, reply with Zelle request for $99
3. Buyer pays → you email the dossier PDF from `butte/delivery/butte_auction_2026-07-31/dossiers/`
4. Turnaround target: <30 min while you're online

**Upgrade to automated Stripe:**
Replace the `mailto:` href in each tile with a Stripe Checkout URL. Set up
one Stripe product per parcel or use dynamic pricing. Webhook triggers auto-email
of the dossier PDF on payment success.

**Files:**
- `index.html` — the marketplace page (90 tiles, static, no backend needed)
- `thumbs/` — aerial thumbnails (53 images)
- `README.md` — this file
