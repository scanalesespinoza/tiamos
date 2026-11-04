"""Single entry point for packaged CLI, background UI, and terminal owners."""
import sys

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'terminal-session':
        sys.argv.pop(1)
        from terminal_session import main
    else:
        from codex_float import main
    main()
