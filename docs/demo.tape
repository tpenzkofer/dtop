# VHS script to record docs/demo.gif  (https://github.com/charmbracelet/vhs)
#
#   brew install vhs        # (pulls ttyd + ffmpeg)
#   vhs docs/demo.tape      # run from the repo root -> writes docs/demo.gif
#
# Uses dtop's built-in --demo data, so no Docker is required.
#
# The committed docs/demo.gif is additionally shrunk with gifski (much smaller
# for gradient-heavy output):
#   ffmpeg -i docs/demo.gif -vf "fps=12,scale=980:-1:flags=lanczos" /tmp/f%04d.png
#   gifski --fps 12 --quality 65 -o docs/demo.gif /tmp/f*.png

Output docs/demo.gif

Set Shell bash
Set FontSize 12
Set Width 1200
Set Height 680
Set Padding 0
Set Framerate 12

# launch the demo
Type "python3 dtop.py --demo"
Sleep 500ms
Enter
Sleep 2500ms

# browse the container list (detail panel + logs follow the selection)
Down
Sleep 700ms
Down
Sleep 700ms
Down
Sleep 1s

# theme showcase — one full loop, ending back on the default (btop)
Type "t"
Sleep 850ms
Type "t"
Sleep 850ms
Type "t"
Sleep 850ms
Type "t"
Sleep 850ms
Type "t"
Sleep 850ms
Type "t"
Sleep 1200ms

# sub-panels below shown in the standard btop coloring
# full log view: open, toggle wrap, close
Type "l"
Sleep 1800ms
Type "w"
Sleep 1400ms
Type "q"
Sleep 500ms

# network view (topology + mermaid diagram)
Type "n"
Sleep 2200ms
Type "q"
Sleep 500ms

# filesystem browser
Type "f"
Sleep 800ms
Down
Down
Enter
Sleep 1500ms
Type "q"
Sleep 900ms

# quit
Type "q"
Sleep 400ms
