# FixtureDB Pipeline Overview Diagram Source Code

```mermaid
flowchart TB
    A["1: GitHub Search"] --> B["2: Repository Cloning"]
    B --> C["3: Test File Detection"]
    C --> D["4: Fixture Extraction"]
    D --> E["5: Metrics &amp; Export"]
    A1["SEART GitHub Search API<br>4 languages, min 500 stars"] --- A
    B1["Quality Filtering<br>Tree-sitter setup<br>Language grammars"] --- B
    C1["Language-specific patterns<br>Test file discovery<br>AST construction"] --- C
    D1["Fixture detection<br>Mock framework scanning<br>Scope analysis"] --- D
    E1["Complexity metrics<br>CSV exports<br>SQLite storage<br>"] --- E

     A1:::phase1
     B1:::phase2
     C1:::phase3
     D1:::phase4
     E1:::phase5
    classDef phase1 fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef phase2 fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef phase3 fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef phase4 fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef phase5 fill:#fce4ec,stroke:#880e4f,stroke-width:2px
```