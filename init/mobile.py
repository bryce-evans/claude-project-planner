"""Expo + React Native + TypeScript scaffold."""

import subprocess
from pathlib import Path

NAME = "Mobile — Expo (React Native + TypeScript)"
DESCRIPTION = "Cross-platform iOS/Android app with Expo, React Native, and TypeScript"
DETECTS = ["app.json", "app.config.ts", "app.config.js", "expo-env.d.ts"]
STACK_NOTES = "Language: TypeScript | Framework: React Native + Expo | Package manager: npm | Targets: iOS + Android"

_TEMPLATES = {
    "1": ("blank-typescript", "Blank — minimal, TypeScript (recommended)"),
    "2": ("tabs",             "Tabs — file-based routing with bottom tab navigator"),
    "3": ("blank",            "Blank — minimal, JavaScript"),
}


def scaffold(target: Path) -> bool:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        print("\n  Node.js is not installed. Install from https://nodejs.org/\n")
        return False

    print("\n  Template:")
    for key, (_, label) in _TEMPLATES.items():
        print(f"    {key}. {label}")
    choice = input("\n  Choice [1]: ").strip() or "1"
    template, label = _TEMPLATES.get(choice, _TEMPLATES["1"])

    print("\n  Additional libraries:")
    add_nav    = input("  React Navigation (stack + tabs)? [Y/n]: ").strip().lower() != "n"
    add_mmkv   = input("  MMKV (fast local storage)? [Y/n]: ").strip().lower() != "n"
    add_query  = input("  TanStack Query (async state / API)? [Y/n]: ").strip().lower() != "n"
    add_zustand = input("  Zustand (global state)? [y/N]: ").strip().lower() == "y"

    print(f"\n  Running: npx create-expo-app@latest . --template {template}\n")
    r = subprocess.run(
        ["npx", "create-expo-app@latest", ".", "--template", template],
        cwd=target,
    )
    if r.returncode != 0:
        return False

    extras: list[str] = []
    if add_nav:
        extras += [
            "@react-navigation/native",
            "@react-navigation/native-stack",
            "@react-navigation/bottom-tabs",
            "react-native-screens",
            "react-native-safe-area-context",
        ]
    if add_mmkv:
        extras.append("react-native-mmkv")
    if add_query:
        extras += ["@tanstack/react-query", "axios"]
    if add_zustand:
        extras.append("zustand")

    if extras:
        print(f"\n  Installing extras...\n")
        subprocess.run(["npx", "expo", "install", *extras], cwd=target)

    # Minimal folder structure
    for d in ["src/components", "src/screens", "src/hooks", "src/services", "src/store"]:
        (target / d).mkdir(parents=True, exist_ok=True)
        (target / d / ".gitkeep").touch()

    print(f"\n  Expo scaffold ready.")
    print(f"    npx expo start          — start dev server (scan QR with Expo Go)")
    print(f"    npx expo run:ios        — build for iOS simulator")
    print(f"    npx expo run:android    — build for Android emulator")
    if add_nav:
        print(f"    React Navigation installed — wrap app in <NavigationContainer>")
    print()
    return True
