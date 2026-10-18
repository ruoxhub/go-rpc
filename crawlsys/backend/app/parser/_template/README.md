# New Platform Template

1. Copy this directory and rename to your platform name.
2. Adjust `platform` class variable and `selectors` dict.
3. Implement `transform(metadata: Metadata) -> Iterator[tuple[str, dict]]` to yield `(kind, dict)` tuples.
   Ensure the dict fields align with the corresponding DTO schema in `crawlstore/src/parser/dto.py` (e.g., ContentDTO, PostDTO).
4. The platform auto-registers via `pkgutil.walk_packages`.
