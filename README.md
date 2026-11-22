# HammerSlip

Free. No account, no sign-in, no subscription. It only contacts Whatnot, and GitHub to
check for updates.

Automatically prints a label with the buyer's username every time something sells in your
Whatnot live show.

- Works with most label printers that are set up on your computer, such as Brother QL and Rollo.
- Supports many label sizes, from small address labels up to 4" × 6" shipping labels.
- Runs on **Windows** and on **Apple Silicon Macs**.

## How it works

HammerSlip connects to your Whatnot account and checks your orders about once a second. As
soon as Whatnot confirms a buyer's payment went through, the label prints. Orders whose
payment fails are listed in the app but never printed.

You run your show exactly as you normally do. The show doesn't even need to be open on the
computer running HammerSlip.

---

## Install

Download the newest version from the [Releases](../../releases/latest) page.

### Windows

1. Run **HammerSlip-Setup-&lt;version&gt;.exe**.
   If Windows shows **"Windows protected your PC"**, click **More info**, then **Run anyway**.
2. Make sure your label printer is installed in Windows and can print a test page.

### Mac (Apple Silicon)

1. Open **HammerSlip-&lt;version&gt;-mac.dmg** and drag **HammerSlip** into **Applications**.
2. The first time you open it, macOS will block it. Go to **System Settings → Privacy &
   Security**, scroll down, click **Open Anyway** and confirm. You only need to do this once
   per new version.
3. Add your label printer in **System Settings → Printers & Scanners** (install the
   manufacturer's Mac driver first if it has one).

### Connect your Whatnot account

1. In Whatnot's developer dashboard, create a **personal access token** with read access to
   **orders**, **shows** and **customers** (customers is what lets HammerSlip see buyers'
   usernames).
2. In HammerSlip, click **Whatnot API…** at the bottom (it opens by itself the first time),
   paste the token and click **Test connection**. It should say *Connected as @yourname*.
3. Click **Save**. The **Whatnot** line at the top turns green.

Keep **Only print sales from my live show** ticked so orders from outside your shows (such
as marketplace sales) don't print.

---

## Set up your printer

1. Open the app and pick your printer from the **Printer** list. It's remembered next time.
2. Click **Printer Settings…** and choose:
   - **Label size:** the size of the labels loaded in your printer.
   - **Orientation:** **Landscape** (text along the long side) or **Portrait** (text along the
     short side). Tick **Flip upside down** if labels come out upside down.
   - **Mac only:** your printer's own options, such as print quality and cutting.
3. Check the preview, click **Test print**, and click **Save** when it looks right.

Settings are saved separately for each printer, so you can switch between printers freely.

> **Windows tip:** if labels come out too small or cut off, also set the same paper size in
> Windows: **Settings → Bluetooth & devices → Printers & scanners →** your printer **→
> Printing preferences**.

---

## Running a show

1. Open **HammerSlip**. The **Whatnot** line says it's waiting for your show to go live.
2. Start your show on Whatnot as usual. The line changes to **Watching your live show**.
3. Click **Start printing sales**. Every paid sale is listed in the app and its label prints
   about 2–3 seconds after the auction ends (Whatnot takes a couple of seconds to confirm
   the payment).

If a payment fails, the sale is listed as **✗ payment failed** and nothing prints. When the
buyer pays on a new try, that order prints like any other.

**Reprinting:** select a sale and click **Print selected** (or double-click it). Hold Ctrl
(⌘ on Mac) to select several. **Print a name…** prints a label for any name you type.

### What's on the label

1. The buyer's username, as large as fits.
2. The item name, or for giveaways the giveaway's title in bold (e.g. **FREE XBOX**).
3. Optional: any text you type into **Bottom line on labels**, such as your channel name.
   Leave it empty for two-line labels.

### Who gets a label

| Setting | Choices |
|---|---|
| **Print Every Sale** *(off by default)* | Off: one label per buyer per session; later sales to the same buyer are listed but don't print. On: every sale prints. |
| **Giveaways:** *(Always Print by default)* | **Always Print:** every giveaway prints. **Never Print:** giveaways never print. **Only if first label:** a giveaway prints only if it's the buyer's first label of the session. |

No order ever prints twice. Each time you open the app, the list of who has a label starts
fresh, and so does the sales log.

### Other options

- **Dark Mode:** switches the app to a dark window.
- **Don't print (save image only):** test without using labels; pictures are saved instead.

All settings are remembered between sessions.

---

## Your files

Everything the app saves is in **Documents › HammerSlip** (the **Open files
folder** button opens it):

| File or folder | What's in it |
|---|---|
| `sales_log.csv` | This session's sales: time, buyer, item and price. Opens in Excel or Numbers. |
| `Sales Logs` | Logs from earlier sessions. |
| `printed_labels` | A picture of every label printed. |

To move to a new computer, install the app there and copy this folder over.

---

## Updating

The app checks for a new version each time it opens. When one is
available, the button at the bottom changes to **Update to …** (you can also click **Check
for updates** any time). Click it when you're not in a show: the app downloads the update,
closes, installs it and reopens by itself. Your settings, sales logs and Whatnot connection
are kept.

Updates come from this repository's [Releases](../../releases) page and are checked against
their published fingerprint before installing, so a damaged or altered download is never
installed.

## Getting help

Click **Save diagnostics…** at the bottom of the app. It saves a file with the app's
settings, versions, printer details and recent messages, and opens the folder it's in. Attach
that file when you [open an issue](../../issues). Buyers' usernames are left out unless you choose to include the
sales log.

## Uninstalling

**Windows:** double-click **Uninstall HammerSlip** in **Documents › HammerSlip** (also in the
Start menu and Settings → Apps). It removes the app and **everything it
saved, including all sales logs and your saved Whatnot token**, so copy any logs you want to
keep first.

**Mac:** drag the app from Applications to the Trash, and delete **Documents › HammerSlip** if
you don't want to keep your settings and logs.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **Whatnot** line is red | Click **Whatnot API…** and **Test connection**. If the token was deleted or mistyped, create a new one and paste it in. |
| Sales list shows **⚠ no buyer name** | Your token can't read customers. Create a token with read access to customers. |
| Line says it's waiting for the show to go live, but you're live | It checks every 20 seconds; give it a moment. |
| "No printers found" | Add the printer to your computer, then click **Refresh** in the app. |
| Labels are the wrong size, cut off or sideways | Check **Printer Settings…** (label size and orientation). On Windows, also see the tip under [Set up your printer](#set-up-your-printer). |
| Labels come out upside down | Tick **Flip upside down** in Printer Settings. |
| A sale was missed while the app was closed | Use **Print a name…** to print it. |
| "Already running" message | The app is already open in another window. |

---

## Building it yourself

HammerSlip is written in Python (Tkinter for the window, Pillow to draw labels). Every push
to `main` is built and tested on GitHub's Windows and Mac machines and, if both pass,
published on the Releases page (see `.github/workflows/build.yml`).

To run it from source: `pip install -r requirements.txt`, then `python app.py`.
To build the installers yourself: `build.ps1` (Windows, needs Nuitka and Inno Setup 6) or
`build_mac.sh` (Apple Silicon Mac, needs Nuitka).

| File | What it does |
|---|---|
| `app.py` | The main window, label rules and printing queue |
| `whatnot_api.py` | Gets new orders from Whatnot and waits for each payment to go through |
| `whatnot_ui.py` | The Whatnot API… window (your access token) |
| `rules.py` | Who gets a label (Print Every Sale, Giveaways) |
| `label.py`, `labelsizes.py` | Drawing labels and the label sizes on offer |
| `printer.py`, `printer_settings.py` | Sending labels to the printer, Printer Settings window |
| `updater.py` | Check for updates |
| `diagnostics.py` | Save diagnostics |
| `paths.py`, `platform_ui.py`, `theme.py` | Where files go, Windows/Mac differences, light and dark mode |
