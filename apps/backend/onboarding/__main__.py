"""`python -m onboarding` — print the default onboarding steps."""

from __future__ import annotations

from onboarding import default_steps


def main() -> None:
    print("onboarding default steps:")
    for i, step in enumerate(default_steps(), 1):
        tag = " (optional)" if step.optional else ""
        print(f"  {i}. [{step.key}]{tag}  {step.prompt}")


if __name__ == "__main__":
    main()
