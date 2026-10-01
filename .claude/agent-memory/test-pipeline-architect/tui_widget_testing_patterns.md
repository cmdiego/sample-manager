---
name: tui-widget-testing-patterns
description: How to test Textual widgets synchronously without pytest-asyncio — mock strategy and patterns used in test_tui_widgets.py
metadata:
  type: project
---

## Textual widget testing without async

pytest-asyncio and anyio are NOT installed. Textual pilot tests (async) are not available.
All widget tests are synchronous using unittest.mock.

### Pattern: mock DOM methods, assert on border_title and Static text

For `update_*` methods that call `mount()`, `remove_children()`, `query_one()`:

1. **patch `Static` in the widget's module namespace** — captures the text passed to each
   `Static(...)` constructor call:
   ```python
   with patch("sample_manager.tui.widgets.top_display.Static") as mock_static, \
        patch.object(widget, "remove_children"), \
        patch.object(widget, "mount"):
       widget.update_focus(item, details)
   texts = " ".join(c.args[0] for c in mock_static.call_args_list if c.args)
   ```

2. **mock `query_one` via `patch.object`** — for widgets that call `self.query_one(selector, type_)`:
   ```python
   mock_label = MagicMock()
   with patch.object(panel, "query_one", return_value=mock_label):
       panel.update_filter("kick")
   mock_label.update.assert_called_once_with("  expected text")
   ```

3. **multi-selector `query_one`** (SessionSummaryWidget) — use `side_effect` with a dict:
   ```python
   mocks = {"#sum-count": MagicMock(), "#sum-size": MagicMock(), "#sum-dest": MagicMock()}
   def side_effect(selector, type_=None):
       return mocks[selector]
   with patch.object(widget, "query_one", side_effect=side_effect):
       widget.update(3, 1024, "/out")
   ```

### Widget construction is always safe (no app needed)

`border_title` and other `__init__`-set attributes can be checked immediately after `Widget()`.
Message classes (e.g., `SampleListWidget.CursorMoved`) are plain Python — instantiate directly.

### Helper: `_all_static_texts(mock_static) -> str`

Collect all first positional args from mock_static.call_args_list as a joined string.
Defined in test_tui_widgets.py and reused across test classes.

### CSS parse smoke test (TestCSS class)

Widget mock tests never load CSS — errors like `border: solid $text` are invisible until the app starts.
Close the gap by parsing `styles/app.tcss` with Textual's own parser + real theme variables:

```python
from textual.app import App
from textual.css.parse import parse, tokenize_values

app = App()
var_tokens = tokenize_values(app.current_theme.to_color_system().generate())
location = ("app.tcss", "app.tcss")
rule_sets = list(parse("", css_text, location, variable_tokens=var_tokens))
errors = [(str(t), str(m)) for rs in rule_sets for t, m in rs.errors]
```

Key gotchas:
- `parse()` accepts `variable_tokens=` (not `variables=`) for theme vars
- `tokenize_values(dict)` converts the `{name: value}` dict to the token format parse expects
- `$text` is valid for `color:` but raises an error when used in `border:` shorthand
- The regression test (`test_border_solid_dollar_text_is_detected_as_invalid`) documents the exact failure mode

### Files written
- `tests/test_tui_widgets.py` — 49 tests (7 _fmt_size, 12 TopDisplay, 8 FiltersPanel, 8 SessionSummary, 6 SelectedFilesList, 5 SampleListWidget messages, 3 TestCSS)
- `tests/test_tui_keybindings.py` — 4 new tests in `TestNewBindings` class (/, escape, tab, ctrl+p)
- `tests/test_tui_data.py` — 9 new tests (6 get_selection_total_size, 3 get_active_destination)

Total suite: 466 → 528 tests, all pass in ~1.5s.
