import sys

if len(sys.argv) > 1 and sys.argv[1] == "--render-mermaid":
    from twomd.mermaid_renderer import main

    del sys.argv[1]
else:
    from twomd.app import main

raise SystemExit(main())
