# claude-agents repo instructions

## Changelog style
Modeled after [cursor.com/changelog](https://cursor.com/changelog).

- **Date + version header**: `## v0.2.0 — Feb 25, 2026`
- **Named feature sections**: `### Feature Name` (not `### Added`)
- **User-benefit tone**: describe what the user *gets*, not what changed internally
- **Short but complete**: 1–3 sentences per feature, code snippet if it helps
- **No bullet soup**: prose paragraphs, not a list of diff lines
- File: `CHANGELOG.md` in repo root, newest version at the top

## Release process
1. Bump `VERSION` in `claude-agents` (e.g. `0.2.0`)
2. Update `CHANGELOG.md` with new entry (Cursor-style)
3. Replace the hero image in `README.md` (line 5, the `<img>` tag) with the latest screenshot
4. Commit: `git commit -m "feat: vX.Y.Z — <headline>"`
5. Tag + push: `git tag vX.Y.Z && git push && git push origin vX.Y.Z`
6. Create GitHub release: `gh release create vX.Y.Z --title "vX.Y.Z — <headline>" --notes "..." --attach screenshot.png`

**README image**: Always swap the hero `<img>` on README line 5 with the latest release screenshot. Ask the user to provide the new GitHub-hosted image URL (upload via the GitHub Release or issue, then copy the URL).

## Versioning
- `PATCH` (0.1.x) — bug fixes only
- `MINOR` (0.x.0) — new features, backward compatible
- `MAJOR` (x.0.0) — breaking changes
