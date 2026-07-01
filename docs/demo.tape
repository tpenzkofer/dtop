# VHS script to record docs/demo.gif  (https://github.com/charmbracelet/vhs)
#
#   brew install vhs        # (pulls ttyd + ffmpeg)
#   vhs docs/demo.tape      # run from the repo root -> writes docs/demo.gif
#
# Uses dtop's built-in --demo data, so no Docker is required.

Output docs/demo.gif

Set Shell bash
Set FontSize 13
Set Width 1280
Set Height 760
Set Padding 0
Set Framerate 15
Set PlaybackSpeed 1.0

# launch the demo
Type "python3 dtop.py --demo"
Sleep 600ms
Enter
Sleep 3s

# browse the container list (detail panel + logs follow the selection)
Down
Sleep 1s
Down
Sleep 1s
Down
Sleep 1500ms

# cycle through the color themes
Type "t"
Sleep 1200ms
Type "t"
Sleep 1200ms
Type "t"
Sleep 1200ms
Type "t"
Sleep 1200ms
Type "t"
Sleep 1500ms

# full log view: open, toggle wrap, close
Type "l"
Sleep 2200ms
Type "w"
Sleep 1600ms
Type "q"
Sleep 700ms

# network view (topology + mermaid diagram)
Type "n"
Sleep 2600ms
Type "q"
Sleep 600ms

# filesystem browser
Type "f"
Sleep 900ms
Down
Down
Enter
Sleep 1800ms
Type "q"
Sleep 1200ms

# quit
Type "q"
Sleep 600ms
