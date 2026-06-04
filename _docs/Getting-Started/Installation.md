# Quick Start: Install bdboard

## What You'll Achieve

bdboard installed on your computer and ready to launch against any project you
track work in.

## Prerequisites

You'll need a few things in place before you install. You only do this once.

- A computer where you can run command-line tools (macOS, Linux, or Windows).
- **bd** (the beads tool) available on your system. bdboard reads your project's
  work items through bd, so it has to be installed and runnable first.
- **Python 3.11 or newer.**
- **uv**, a fast Python installer and environment manager.
- The project folder you want to look at — the one your team tracks work in. It
  contains a hidden `.beads` folder.

> [!NOTE]
> bdboard never changes your project's work items on its own. It reads them and
> shows them. The only thing *you* can change from the board is an individual
> field on an open item, and only when you choose to.

## Step 1: Get the project folder

Open a terminal and go into the folder your team uses to track work — the one
that contains a `.beads` folder.

```sh
cd path/to/your-project
```

**Expected result:** your terminal is now "inside" the project folder.

> [!TIP]
> Not sure you're in the right place? Listing the folder's contents should show
> a `.beads` entry. That hidden folder is what bdboard reads from.

## Step 2: Install bdboard

From inside the project folder, install bdboard with uv:

```sh
uv venv
uv pip install -e .
source .venv/bin/activate
```

**Expected result:** the commands finish without errors, and your terminal
prompt changes to show the active environment. bdboard is now installed for this
project.

> [!NOTE]
> If your organization uses a private package mirror, ask whoever set the
> project up for the one extra setting you may need. Everything else stays the
> same.

## Step 3: Hydrate the work history (first time only)

A freshly copied project may not include the work history yet. If your board
later looks empty, pull the history in once:

```sh
bd bootstrap --yes
```

**Expected result:** bd downloads the project's work history. You only do this
the first time you set up a fresh copy.

## Step 4: Confirm it runs

Launch bdboard:

```sh
bdboard
```

**Expected result:** bdboard starts and a browser tab opens showing your
project's board. The terminal prints the address it's serving so you can reopen
the tab any time.

> [!TIP]
> Want to keep the tab from opening automatically, or point bdboard at a
> different project folder? See the launch options in the
> [Quick Start](QuickStart.md).

## Common Issues

| Symptom | What to do |
|---------|------------|
| The board opens but every lane shows an error | bd isn't installed or isn't on your system path. Install bd, then run `bdboard` again. |
| The board is completely empty | The project history hasn't been pulled in yet. Run `bd bootstrap --yes`, then refresh. |
| `bdboard` is "not found" after install | The environment isn't active in this terminal. Run `source .venv/bin/activate` and try again. |
| A message about Python version | You need Python 3.11 or newer. Update Python, then reinstall. |

## What You Learned

You installed bdboard, pulled in your project's work history, and confirmed the
board opens.

## Next Steps

- Open your first board and learn the layout in the
  [Quick Start](QuickStart.md).
- Then learn everyday tasks in the [Guides](../Guides/index.md).
- New to the whole idea? Read the [Overview](../Overview.md).
