# Ontology Map Toolkit — Direction Document

> Documento de direcao estrategica para transformar o toolkit de "demo impressionante"
> em "produto que muda a vida de quem usa e define um novo standard na industria."
>
> Status: AWAITING APPROVAL
> Data: 2026-02-27
> Autores: Gustavo Schneiter + Claude Opus 4.6

---

## 1. Tese Central

**O Ontology Map Toolkit nao e mais um graph visualizer. E o nascimento de uma nova
categoria: Spatial Software Engineering.**

Nenhuma ferramenta no mercado combina:
- Interface espacial 3D com semantic zoom fractal (sistema → modulo → arquivo → funcao → codigo)
- Zero-config inference (dados entram, cockpit sai — sem perguntas)
- AI agent que NAVEGA o mapa (nao so responde perguntas)
- Static export offline (abre sem servidor, compartilha como anexo)
- Leve o suficiente para browser (< 250 KB initial load)

**O problema e que ninguem sabe disso ainda.** Porque falta a porta de entrada.

---

## 2. Diagnostico Honesto: Onde Estamos

### O que ja e SOTA (genuinamente unico)

| Componente | LOC | Status | Diferencial |
|-----------|-----|--------|-------------|
| Inference Engine | 1,023 | Completo, 71 tests | Unico no mercado — zero-config cockpit |
| 3D Rendering | 4,399 | Production-ready | Three.js r162, bloom, LOD, instanced |
| Design System | 2,053 CSS + 498 JS | OKLCH nativo | Primeiro framework 3D com OKLCH |
| Drill-Down Fractal | 2,510 | 5 niveis | Nenhum competidor faz isso |
| Static Export | ~200 | Funcional | Abre offline, compartilhavel |
| Accessibility | 758 | WCAG AA | 23 E2E tests, skip-link, ARIA |
| State Management | 102 | Elegante | Proxy-based reactive, zero deps |
| Knowledge Library | 1,444 | Feature-complete | Faceted filtering, 6 view modes |
| **TOTAL** | **~22,000** | **85% done** | |

### O que FALTA (e por que impede o "wow")

| Gap | Impacto | Por que importa |
|-----|---------|-----------------|
| **Import Adapters** | BLOQUEANTE | Sem isso, usuario precisa criar JSON na mao. Nao existe "primeiro minuto magico" |
| **Agent Navigation** | ALTO | Chat panel existe mas AI nao consegue navegar o mapa. Feature mais pedida |
| **Momento "Holy Shit"** | ALTO | Nada no produto gera screenshot viral. Precisa de 1 feature visceral |
| **README/Landing** | ALTO | Dev vê o repo e nao entende o que é em 7 segundos |
| **Exemplos** | MEDIO | So 1 exemplo (Engineering Brain). Precisa de 3-4 para diferentes dominios |

---

## 3. Pesquisa: Dores Reais dos Usuarios

### 3.1 Os Numeros que Importam

| Dado | Fonte | Implicacao |
|------|-------|------------|
| 67% dos devs herdam codebases sem contexto | Stack Overflow 2024 | Problema universal, nao de nicho |
| 3 meses para ser produtivo num codebase novo | Industry average | Time-to-understanding e a metrica-chave |
| 62% citam tech debt como frustacao #1 | Stack Overflow 2024 | Mas o problema real e VISIBILIDADE do debt |
| 30% pedem AI com codebase awareness | Qodo State of AI 2025 | Devs querem AI que entende ESTRUTURA, nao so arquivos |
| 80% dos devs estao infelizes no trabalho | Stack Overflow 2024 | Ferramentas que causam JOY tem vantagem desproporcional |
| 42% mais produtivos quando entendem o codigo | Multiplayer research | Compreensao > velocidade de digitacao |

### 3.2 As 5 Dores Estruturais

**DOR 1: "Onde estou neste codebase?"**
Dev novo entra num projeto com 500 arquivos. Abre o IDE. Vê uma arvore de pastas.
Nao entende NADA da arquitetura. Nao sabe por onde comecar. Leva semanas.

→ **Nos resolvemos**: `ontology-map render .` → mapa 3D do projeto em 30 segundos.
→ **Hoje nao resolve**: porque o comando `render` e um stub.

**DOR 2: "Se eu mudar isso, o que quebra?"**
Dev quer refatorar um modulo. Nao tem como visualizar o blast radius.
Dependency-cruiser gera um diagrama 2D estatico. CodeScene mostra metricas.
Ninguem mostra o IMPACTO FISICAMENTE.

→ **Nos resolvemos**: Dependency Earthquake — clicar num node e ver a cascata.
→ **Hoje nao resolve**: feature nao existe.

**DOR 3: "A documentacao de arquitetura ta morta"**
Diagrama no Draw.io/Miro desatualizado no dia seguinte. Ninguem mantem.
IcePanel/Structurizr exigem manutencao manual. Backstage e catalogo, nao visual.

→ **Nos resolvemos**: Mapa gerado direto do codigo — sempre atualizado.
→ **Hoje nao resolve**: sem import adapters = sem geracao automatica.

**DOR 4: "O AI nao entende meu projeto"**
Cursor ve arquivos. Copilot ve o buffer. Nenhum ve a TOPOLOGIA do sistema.
30% dos devs pedem mais codebase awareness. E a feature mais pedida.

→ **Nos resolvemos**: AI agent com graph awareness que navega o mapa espacial.
→ **Hoje resolve parcialmente**: chat funciona, mas tools nao navegam.

**DOR 5: "Quero mostrar a arquitetura pro time/cliente mas nao tenho como"**
Apresentacoes com boxes e setas feitas na mao. Incompletas. Chatas.
Ninguem consegue mostrar a complexidade real de forma bonita e interativa.

→ **Nos resolvemos**: Static export — HTML offline, abre em qualquer browser.
→ **Hoje resolve**: 100% funcional.

---

## 4. Pesquisa: O Que Funciona em Dev Tools SOTA

### 4.1 Licoes dos Melhores

| Produto | Licao | Aplicacao para nos |
|---------|-------|--------------------|
| **Cursor** | $0 marketing, $1.2B ARR. 36% free→paid. Import VS Code = zero friction. Indexa codebase automaticamente. | Nosso `render .` deve funcionar como o auto-index: zero config, resultado imediato |
| **Linear** | $35K lifetime marketing. Keyboard-first. Speed = identity. "Workbench, not chatbot" para AI | AI no mapa deve ser WORKBENCH (structured), nao chatbot (open-ended) |
| **Vercel** | < 30s para primeiro deploy. Template/starter-kit > docs | Precisamos de starter-kits: `ontology-map init --template microservices` |
| **Figma** | 2 anos gratis antes de cobrar. "Gate conversion, not adoption." Multiplayer = adoption driver | Free forever para individual. Sharing/collab = trigger de upgrade |
| **Tailwind** | Retencao 75% (quem tenta, fica). Venceu o hate com blog posts profundos | Devs vao estranhar 3D no inicio. Conteudo tecnico profundo vence resistencia |
| **Charm** | "Make the command line glamorous." Polish composto. Cada tool faz 1 coisa linda | Cada feature nossa deve ter polish Charm-level. Sound, animacao, personalidade |
| **Warp** | AI agents = 30x revenue. Campus ambassadors | AI navigation e o multiplicador. Foco em early-career devs |

### 4.2 Licoes Academicas

| Paper/Projeto | Finding | Aplicacao |
|---------------|---------|-----------|
| CodeCity VR (2023) | Usuarios completam tasks MAIS RAPIDO em 3D que 2D. Memoria espacial real | Validacao cientifica que 3D nao e gimmick — e vantagem cognitiva |
| ExplorViz Semantic Zoom (2025) | 15/16 usuarios PREFEREM semantic zoom. Mini-map para teleportacao | Nosso drill-down esta certo. Adicionar mini-map |
| Visualization-of-Thought (NeurIPS 2024) | ATÉ LLMs raciocinam melhor com representacao espacial | AI + spatial = vantagem composta |
| CodeScene Behavioral Analysis | Hotspots = 25-70% dos defeitos. Git history + structure = insight | Integrar git blame/churn como overlay no mapa |
| Sonification STAR (2024) | Speech+tone hybrids > beeps. Audio engaja mais que silencio | Sound design com voz + tons, nao earcons genericos |

### 4.3 O que Mata Dev Tools

| Anti-pattern | Exemplo | Como evitamos |
|-------------|---------|---------------|
| Tool proliferation fatigue | "Mais uma ferramenta pra aprender" | SUBSTITUIMOS ferramentas, nao adicionamos. Replace Draw.io, not complement it |
| Broken first experience | Bug no primeiro uso = usuario perdido para sempre | Testes E2E no onboarding path. Se `render .` falhar, game over |
| Feature overload | Muita coisa na tela, nada claro | Progressive disclosure: dashboard → mapa → detalhe → codigo |
| Premature monetization | Cobrar antes de criar habito | Free para sempre em uso individual. Pagar so por team features |
| "Vaporware vibes" | README lindo, produto vazio | So prometemos o que JA funciona. Roadmap separado |

---

## 5. Pesquisa: Stack Tecnico para Import Adapters

### 5.1 Melhor Abordagem: tree-sitter + Language-Specific Deep Analysis

| Tier | Tecnologia | O que extrai | Esforco |
|------|-----------|-------------|---------|
| **1 (Universal)** | tree-sitter (40+ langs) | Funcoes, classes, imports, call sites | BAIXO — pip install |
| **1 (Universal)** | PyYAML | docker-compose → service graph | TRIVIAL |
| **1 (Universal)** | python-hcl2 | Terraform → resource graph | BAIXO |
| **2 (Deep)** | PyCG/JARVIS | Python call graph (99.2% precision) | BAIXO — JSON output |
| **2 (Deep)** | dependency-cruiser | JS/TS module graph (JSON schema) | BAIXO — npx |
| **3 (API)** | openapi3 | OpenAPI → endpoint graph | BAIXO |
| **3 (API)** | graphql-core | GraphQL → type graph | BAIXO |
| **3 (API)** | proto-schema-parser | Protobuf → service graph | BAIXO |
| **4 (Runtime)** | OpenTelemetry | Live service dependency map | MEDIO |

### 5.2 Referencia: Como o Aider Faz (Gold Standard)

Aider's RepoMap: tree-sitter → NetworkX graph → PageRank → contexto rankado.
Funciona para 40+ linguagens sem config. Exatamente o modelo que devemos seguir.

### 5.3 Prioridade de Adapters

| Adapter | Usuarios potenciais | Prioridade |
|---------|-------------------|------------|
| Python (tree-sitter + PyCG) | Backend devs, ML/AI teams | P0 |
| TypeScript/JS (tree-sitter + dep-cruiser) | Frontend devs, full-stack | P0 |
| docker-compose (PyYAML) | DevOps, infra teams | P0 |
| OpenAPI (openapi3) | API-first teams | P1 |
| Terraform (python-hcl2) | Cloud/infra teams | P1 |
| Go (tree-sitter + go mod graph) | Backend teams | P1 |
| Kubernetes (PyYAML + schema) | Platform teams | P2 |
| GraphQL (graphql-core) | API teams | P2 |

---

## 6. Pesquisa: WebXR State of the Art (2026)

| Capability | Status | Implicacao |
|-----------|--------|------------|
| Apple Vision Pro WebXR | ON by default (visionOS 2+). Gaze-and-pinch nativo | Podemos rodar no Vision Pro SEM app nativa |
| Three.js WebGPU | r171+, fallback automatico WebGL2. 100x performance em point clouds | 10K+ nodes a 60fps garantido |
| WebSpatial API (W3C) | Proposta 2025. HTML/CSS com Z-axis + spatial events | Futuro: UI 2D vira 3D sem Three.js. Progressive enhancement |
| React Three XR | Prodution-ready. Familiar (React patterns) | Se migrarmos para React no futuro |

**Decisao**: WebXR e viavel HOJE com nosso stack (Three.js). Nao e futuro — e presente.
Mas e P2. O hook (adapters) vem primeiro.

---

## 7. Estrategia de Produto: A Jornada do "WOW"

### 7.1 O Framework dos 4 Momentos

```
MOMENTO 1: HOOK (primeiros 60 segundos)
"Isso existe?!" → O dev descobre o produto

MOMENTO 2: AHA (primeiros 5 minutos)
"Wait... it just works?!" → O dev vê SEU projeto em 3D

MOMENTO 3: HOLY SHIT (primeiros 30 minutos)
"Ninguem mais faz isso" → Uma feature que nao existe em lugar nenhum

MOMENTO 4: LOVE (primeira semana)
"Nao consigo voltar" → O dev incorpora no workflow diario
```

### 7.2 Mapeamento: Features → Momentos

| Momento | Feature | Status Hoje | Target |
|---------|---------|-------------|--------|
| **HOOK** | README com GIF epico + install 1 linha | README existe mas sem GIF | Wave 0 |
| **AHA** | `ontology-map render .` → mapa 3D do SEU projeto | Stub (0%) | Wave 1 |
| **AHA** | Inference infere TUDO automaticamente | Funciona (100%) | Pronto |
| **HOLY SHIT** | Dependency Earthquake (cascata de impacto) | Nao existe (0%) | Wave 2 |
| **HOLY SHIT** | AI navega o mapa (zoom, highlight, explain) | Parcial (60%) | Wave 1 |
| **LOVE** | Live Code Pulse (nodes pulsam com commits) | Nao existe (0%) | Wave 3 |
| **LOVE** | Ghost Mode (debt visivel como fantasmas) | Nao existe (0%) | Wave 3 |
| **LOVE** | Sound Design (audio imersivo, sci-fi ambient) | Nao existe (0%) | Wave 2 |

### 7.3 A Narrativa

> **"See your software. Understand it. Change it."**
>
> Ontology Map Toolkit is the spatial interface for software engineering.
> Point it at any project. Get a 3D map in 30 seconds. Drill down to the code.
> Ask the AI. Share it as a file.
>
> No config. No login. No bullshit.

---

## 8. Waves de Implementacao

### Wave 0: "The Hook" (README + Onboarding)
**Objetivo**: Dev vê o repo e quer tentar em < 7 segundos.

| Item | Descricao |
|------|-----------|
| README rewrite | Hero GIF (3s loop), one-liner, install 1 linha, 3 screenshots |
| GIF de demo | Screen recording: `ontology-map render .` → mapa 3D aparece |
| Landing page | GitHub Pages com demo interativa (static export embedado) |
| Starter templates | `ontology-map init --template {microservices,monolith,pipeline,api}` |
| Examples directory | 4 exemplos completos (engineering-brain, fastapi-app, react-app, infra) |

### Wave 1: "The Aha" (Import Adapters + Agent Navigation)
**Objetivo**: Dev roda `ontology-map render .` e ve o projeto dele em 3D. AI navega.

| Item | Descricao | Esforco |
|------|-----------|---------|
| **Adapter framework** | Plugin architecture para adapters (detect → extract → normalize) | M |
| **Python adapter** | tree-sitter + PyCG → graph.json. Modules, classes, functions, imports, call graph | L |
| **JS/TS adapter** | tree-sitter + dependency-cruiser → graph.json | L |
| **docker-compose adapter** | PyYAML → service graph com networks, volumes, deps | S |
| **CLI render** | `ontology-map render ./path` — auto-detect language, run adapter, serve | M |
| **CLI inspect** | `ontology-map inspect ./path` — mostra config efetiva com origem | S |
| **Agent tool wiring** | 5 tools (inspect_node, search, navigate, highlight, explain) → state mutations | M |
| **Agent system prompt** | Graph-aware: node count, edge types, clusters, current selection | S |

### Wave 2: "The Holy Shit" (Features que Ninguem Tem)
**Objetivo**: Dev experimenta algo que nao existe em nenhum outro lugar.

| Item | Descricao | Esforco |
|------|-----------|---------|
| **Dependency Earthquake** | Click node → BFS cascata → particulas de impacto propagam pelo grafo. Shake physics. Color by impact depth. Counter "N nodes affected" | L |
| **Sound Design** | Ambient sci-fi low hum. Swoosh no drill-down. Ping na selecao. Rumble no earthquake. Volume proporcional ao zoom. Web Audio API | M |
| **Mini-map** | Radar no canto com visao top-down do grafo inteiro. Click para teleportar. Highlight zona atual | M |
| **Heatmap Mode** | Toggle overlay: recolorir nodes por metrica (complexity, churn, coverage, last-modified). Gradient perceptual OKLCH | M |
| **Git Blame Overlay** | Cores por autor. Nodes pulsam com frequencia de commit (churn). Bus factor warning | M |

### Wave 3: "The Love" (Features que Criam Habito)
**Objetivo**: Dev incorpora no workflow diario. Nao consegue voltar.

| Item | Descricao | Esforco |
|------|-----------|---------|
| **Live Code Pulse** | WebSocket/polling conecta ao git repo. Nodes pulsam quando arquivo muda. CI status como aura (verde/vermelho). PR como edge temporaria | XL |
| **Ghost Mode** | Nodes fantasma translucidos para: TODOs prometidos, tests faltando, docs ausentes, RFs nao implementados. Spectral shader | L |
| **What-If Sandbox** | Fork o grafo. Drag nodes entre modulos. Criar/deletar edges. Diff visual side-by-side. Export como RFC | XL |
| **Time-Travel Slider** | Slider temporal: ver como a arquitetura evoluiu commit a commit. Playback animado | XL |
| **Annotation Layer** | Post-its 3D ancorados em nodes. Flags, pins, highlights persistentes. Export com anotacoes | M |

### Wave 4: "The Standard" (Ecossistema)
**Objetivo**: Outros devs constroem em cima. Comunidade se forma.

| Item | Descricao | Esforco |
|------|-----------|---------|
| **Plugin System** | iframe sandbox + postMessage API. Manifest schema. Plugin registry | XL |
| **Shape Packs** | AWS icons, K8s icons, DB icons, UML shapes. Community-contributed | M |
| **Theme Marketplace** | VSCode themes funcionam. Community themes | M |
| **Multi-Map Federation** | Varios projetos conectados num meta-mapa. Cross-repo navigation | XL |
| **WebXR Mode** | Apple Vision Pro / Meta Quest support. Walk inside your architecture | XL |
| **Embed Mode** | `<iframe src="ontology-map.dev/embed/...">` em qualquer pagina | M |
| **Terminal Mode** | TUI via Textual (Python). ASCII art 3D. SSH-friendly | L |

---

## 9. Principios de Design (Charm-Inspired)

### 9.1 Developer Delight > Feature Count

Cada feature que implementamos deve ter:
- **Animacao impecavel** — transicoes suaves, easing Material 3, nada pula
- **Feedback instantaneo** — < 100ms para qualquer acao
- **Personalidade** — mensagens de erro com tom humano, nao "Error 500"
- **Sound** (Wave 2+) — audio reforça a experiencia espacial

### 9.2 Opinionated by Default, Configurable by Choice

Nao perguntamos. Inferimos. Se o dev quiser mudar, pode via schema.
Isso e On-Rails Design e e o que nos diferencia de TODA a competicao.

### 9.3 Replace, Don't Add

Nao somos "mais uma ferramenta". Substituimos:
- Draw.io/Miro para diagramas de arquitetura
- Dependency-cruiser para visualizacao de dependencias
- README architecture sections para documentacao visual
- Backstage software catalog para discovery (futuro)

### 9.4 Speed is a Feature

Se o mapa demora > 2s para abrir, perdemos o usuario.
Se o drill-down tem lag, a magia morre.
Performance nao e otimizacao — e requisito de produto.

### 9.5 Keyboard-First, Mouse-Welcome

Toda acao principal via teclado:
- `Cmd+K` → busca
- `Escape` → voltar
- `Enter` → drill-in
- `Space` → toggle detail
- `D` → dependency earthquake
- `H` → heatmap toggle
- `G` → ghost mode toggle

---

## 10. Modelo de Negocio (Futuro)

### Inspirado em Figma + Cursor

```
FREE (forever, individual):
├── Todas as features core
├── Import adapters (todos)
├── Static export
├── AI agent (BYOK — traz sua propria key)
├── 1 projeto ativo
└── Community themes/shapes

PRO ($15/mes, individual):
├── Projetos ilimitados
├── Live Code Pulse (git integration)
├── Time-Travel Slider
├── Priority support
└── Custom themes/shapes

TEAM ($25/user/mes):
├── Multi-Map Federation
├── Shared annotations
├── Team AI (API key compartilhada)
├── SSO/SAML
├── Audit log
└── Custom branding

ENTERPRISE (contato):
├── On-prem deployment
├── Plugin development support
├── SLA
└── Custom adapters
```

**Principio Figma**: Gate conversion (projetos), not adoption (features).
Free tier deve ser genuinamente util, nao crippled.

---

## 11. Metricas de Sucesso

### Produto

| Metrica | Target | Como medir |
|---------|--------|------------|
| Time to first map | < 60 segundos | `pip install` → `render .` → browser abre |
| "Aha" conversion | > 60% dos que tentam, fazem drill-down | Analytics (se opt-in) |
| GitHub stars (6 meses) | 5,000+ | GitHub |
| Weekly active users | 1,000+ | Analytics |
| Retencao D7 | > 40% | Analytics |
| NPS | > 50 | Survey |

### Qualidade

| Metrica | Target | Como medir |
|---------|--------|------------|
| Time to first paint | < 2s | Lighthouse |
| 10K nodes @ 60fps | Sim | Benchmark |
| Test coverage (JS) | > 80% | Istanbul |
| Test coverage (Python) | > 90% | pytest-cov |
| WCAG AA compliance | 100% | axe-core |
| Bundle size (gzip) | < 250 KB initial | webpack-bundle-analyzer |

---

## 12. Riscos e Mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| tree-sitter nao extrai suficiente para graph bonito | Media | Alto | Fallback para import + call graph heuristics. PyCG como backup |
| Performance degrada > 5K nodes | Baixa | Alto | InstancedMesh, LOD, WebGPU upgrade path. Benchmarks em CI |
| Devs rejeitam 3D como "gimmick" | Media | Alto | Conteudo tecnico profundo (papers, benchmarks). SVG 2D fallback |
| Overengineering das Waves 3-4 | Alta | Medio | Ship Wave 1 primeiro. Validar com usuarios. Iterar baseado em dados |
| AI agent custa muito (API keys) | Media | Medio | BYOK model. Estimativa de custo na UI. Cache de respostas |

---

## 13. Cronograma Sugerido

```
Wave 0 — The Hook .............. 1 semana
Wave 1 — The Aha ............... 3-4 semanas
Wave 2 — The Holy Shit ......... 3-4 semanas
Wave 3 — The Love .............. 4-6 semanas
Wave 4 — The Standard .......... ongoing

MVP para lancamento publico: Wave 0 + Wave 1 (4-5 semanas)
```

---

## 14. Decisoes para Aprovar

| # | Decisao | Opcoes | Recomendacao |
|---|---------|--------|--------------|
| D1 | Sequencia de Waves | Como descrito vs outro order | Como descrito (Hook→Aha→Holy Shit→Love→Standard) |
| D2 | Prioridade de adapters | Python+JS primeiro vs Docker+API primeiro | Python+JS+Docker (P0), API specs (P1) |
| D3 | AI agent approach | Workbench (structured tools) vs Chatbot (free-form) | Workbench — Linear provou que structured > chat |
| D4 | Sound design | Incluir em Wave 2 vs postergar | Incluir — e o toque Charm que gera amor |
| D5 | Dependency Earthquake | Wave 2 vs Wave 1 | Wave 2 — adapters sao bloqueantes, earthquake e wow |
| D6 | Modelo de negocio | Free individual + paid team vs full open source | Free individual + paid team (sustentabilidade) |
| D7 | Nome do produto | "Ontology Map Toolkit" vs outro nome | Discutir — "Ontology Map" e tecnico demais? |
| D8 | WebXR | Wave 2 (early) vs Wave 4 (late) | Wave 4 — nao bloqueia adocao, e cherry on top |

---

## 15. Competidores Revisitados: Onde Ganhamos

```
┌──────────────────────┬──────┬──────┬──────┬──────┬──────┬──────┬──────────┐
│ Capability           │ NOS  │ Neo4j│ Gephi│IceP. │CodeS.│Backst│ Cursor   │
├──────────────────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────────┤
│ 3D Spatial           │  ✅  │  ❌  │  ❌  │  ❌  │  ❌  │  ❌  │   ❌     │
│ Zero-config inference│  ✅  │  ❌  │  ❌  │  ❌  │  ❌  │  ❌  │   ✅     │
│ Semantic zoom (5 lvl)│  ✅  │  ❌  │  ❌  │  ✅  │  ❌  │  ❌  │   ❌     │
│ AI agent spatial     │  ✅  │  ❌  │  ❌  │  ❌  │  ❌  │  ⚠️  │   ✅*    │
│ Static export        │  ✅  │  ❌  │  ❌  │  ❌  │  ❌  │  ❌  │   ❌     │
│ < 250 KB initial     │  ✅  │  ❌  │  ❌  │  ❌  │  N/A │  ❌  │   ❌     │
│ OKLCH color science  │  ✅  │  ❌  │  ❌  │  ❌  │  ❌  │  ❌  │   ❌     │
│ Sound design         │  🔜  │  ❌  │  ❌  │  ❌  │  ❌  │  ❌  │   ❌     │
│ Impact simulation    │  🔜  │  ❌  │  ❌  │  ❌  │  ❌  │  ❌  │   ❌     │
│ WebXR ready          │  🔜  │  ❌  │  ❌  │  ❌  │  ❌  │  ❌  │   ❌     │
│ Free & open source   │  ✅  │  ❌  │  ✅  │  ❌  │  ❌  │  ✅  │   ❌     │
└──────────────────────┴──────┴──────┴──────┴──────┴──────┴──────┴──────────┘

* Cursor tem AI com codebase awareness mas nao tem interface espacial
```

---

## 16. Fontes da Pesquisa

### Developer Pain Points & Surveys
- [Stack Overflow Developer Survey 2024](https://stackoverflow.blog/2025/01/01/developers-want-more-more-more-the-2024-results-from-stack-overflow-s-annual-developer-survey/)
- [80% of Developers Unhappy — ShiftMag](https://shiftmag.dev/unhappy-developers-stack-overflow-survey-3896/)
- [Qodo State of AI Code Quality 2025](https://www.qodo.ai/reports/state-of-ai-code-quality/)
- [Multiplayer — Developer Onboarding](https://www.multiplayer.app/blog/improving-developer-onboarding/)
- [Atlassian State of Developer Experience 2024](https://www.atlassian.com/software/compass/resources/state-of-developer-2024)

### Developer Tool Growth Stories
- [Cursor: $0 Marketing to $1.2B ARR](https://taptwicedigital.com/stats/cursor)
- [Linear: $35K Lifetime Marketing to $400M Valuation](https://www.eleken.co/blog-posts/linear-app-case-study)
- [Vercel: DX-Powered $200M Growth](https://www.reo.dev/blog/how-developer-experience-powered-vercels-200m-growth)
- [Figma: 5 Phases of Community-Led Growth](https://review.firstround.com/the-5-phases-of-figmas-community-led-growth-from-stealth-to-enterprise/)
- [Tailwind: From Hate to 75% Retention](https://mattrickard.com/why-tailwind-css-won)

### Design Philosophy & Developer Delight
- [Does Developer Delight Matter? — Charm's Crush](https://tessl.io/blog/does-developer-delight-matter-in-a-cli-the-case-of-charm-s-crush/)
- [Linear: Design for the AI Age](https://linear.app/now/design-for-the-ai-age)
- [Charmbracelet on GitHub](https://github.com/charmbracelet)

### Academic — Software Visualization
- [CodeCity VR vs On-Screen (2023)](https://www.sciencedirect.com/science/article/pii/S0950584922001732)
- [Semantic Zoom in Software Cities (2025)](https://arxiv.org/abs/2510.00003)
- [ExplorViz — Live Trace Visualization](https://explorviz.dev/)
- [Visualization-of-Thought — NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/a45296e83b19f656392e0130d9e53cb1-Paper-Conference.pdf)

### Technology Stack — Import Adapters
- [Aider RepoMap (tree-sitter + PageRank)](https://aider.chat/2023/10/22/repomap.html)
- [PyCG — Python Call Graph (99.2% precision)](https://github.com/vitsalis/PyCG)
- [dependency-cruiser — JS/TS module graph](https://github.com/sverweij/dependency-cruiser)
- [python-hcl2 — Terraform parser](https://github.com/amplify-education/python-hcl2)
- [SCIP Protocol — Sourcegraph indexing](https://github.com/sourcegraph/scip)

### WebXR & Spatial Computing
- [Natural Input for WebXR — Apple Vision Pro](https://webkit.org/blog/15162/introducing-natural-input-for-webxr-in-apple-vision-pro/)
- [Three.js WebGPU Support](https://www.utsubo.com/blog/threejs-2026-what-changed)
- [WebSpatial API (W3C 2025)](https://webspatial.dev/)

### Sound Design
- [Sound Effects in Claude Code](https://alexop.dev/posts/how-i-added-sound-effects-to-claude-code-with-hooks/)
- [Sonification + Visualization STAR 2024](https://onlinelibrary.wiley.com/doi/10.1111/cgf.15114)

### Business Model
- [Pricing Developer Tools — Heavybit](https://www.heavybit.com/library/article/pricing-developer-tools)
- [Why 90% of Developer SaaS Tools Fail](https://medium.com/@coders.stop/why-90-of-developer-saas-tools-fail-in-year-two-analysis-of-50-failed-startups-691fa3dd7961)

---

*DIRECTION v1.0 — 2026-02-27*
*Ontology Map Toolkit — The Spatial Interface for Software Engineering*
