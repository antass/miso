# Miso — your cookbooks, searchable

**Start it:** double-click `Miso.command`. Your browser opens at http://localhost:8137. Keep that Terminal window open while you use Miso.

**On the kitchen iPad:** connect to the same Wi-Fi and open the address shown in Settings (⚙), for example `http://<your-mac>.local:8137`. Then tap Share → Add to Home Screen.

## What it does
- **Search** every recipe in your EPUB/MOBI cookbooks by title, ingredient, or book. Each result shows the cover of the book it came from.
- **Filters:** course, protein, diet, method (air fryer, slow cooker, freezer-friendly, make-ahead…), time, source, your own tags, and ingredients to include or leave out.
- **Tags:** add your own (Kid-approved, Weeknight…) on any recipe, then filter by them.
- **Everything** searches your cookbooks and saved recipes, plus live results from NYT Cooking, EatingWell, Love & Lemons, Skinnytaste and Yummy Toddler Food. You can also search any one site on its own. Yummy Toddler Food blocks apps from reading its recipe pages, so save those with the Save to Miso bookmark (Settings). Tap a result to import it. Imported recipes stay searchable offline.
- **Paste any recipe link** into the search box to import it. This works on most recipe sites.
- **Cook mode:** keeps the screen awake, makes the text bigger, and adds a step-by-step bar. You can also use ←/→ or Space on a keyboard.
- Tap ingredients to **check them off**. Tap a step to **highlight where you are**.
- **Timers:** tap any time in a step (for example "⏱ 20 minutes") to start a countdown with an alarm.
- **Scale** any recipe to ½×, 2× or 3×.
- **Shopping list:** builds from one recipe or your whole week. Items are grouped by store aisle, and salt, pepper and oil are unchecked by default. Use Copy or Share to send it to Notes or Reminders.
- **Meal plan:** a week view. Pick a day on a calendar and add a recipe, or just write the meal ("Leftovers", "Pizza night"). Each meal has a "+ Google Calendar" button, and you can export the whole week as an `.ics` file.
- **Saved:** your ★ Favorites and every recipe you've saved from a website, in one tab.
- **Your usual filters:** the filter combinations you use most show up under Browse.
- **My notes**, your own **star ratings**, and a **Cooked ×N** log on every recipe.

## Where things live
- `config.json` lists the folders that get scanned. Books are read straight from Google Drive for Desktop (`GoogleDrive-*` covers every signed-in account). Edit it, then use Settings → "Rescan for new books".
  - `library_folders` are cookbook-only folders.
  - `mixed_folders` hold all kinds of books, such as a Calibre library. A book from one of these only counts if it has at least 10 recipes.
- `data/state.json` stores your list, plan, favourites, notes, and saved web recipes. It syncs through iCloud.
- The recipe index and covers are cached in `~/Library/Application Support/Miso`. You can delete this cache at any time; it rebuilds itself.
- MOBI and AZW3 files are converted with Calibre's `ebook-convert`, which is already installed.

## If a book is missing
Library → "files couldn't be used" lists any file that is empty or that the cloud drive didn't download. To fix one, copy a good copy of the book into `Hobbies/Cookbooks`.
