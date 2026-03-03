/// Ontology Map — Spatial Software Engineering in your terminal.
#[derive(clap::Parser, Debug)]
#[command(
    name = "ontology-map",
    version,
    about = "Ontology Map — Terminal UI for spatial code architecture visualization",
    long_about = "Visualize your codebase as a force-directed graph in the terminal.\n\n\
        Supports: Python, JavaScript/TypeScript, Go, Rust, Java, C#, Docker Compose.\n\
        Features: Braille-rendered graph, fuzzy search, git time-travel, churn heatmap,\n\
        blame overlay, live reload on file save.\n\n\
        Keybinds: hjkl/arrows=pan, +/-=zoom, Tab=cycle nodes, /=search, t=time-travel,\n\
        c=churn, b=blame, e=edges, n=labels, q=quit"
)]
pub struct Cli {
    /// Path to the project to analyze (defaults to current directory)
    #[arg(default_value = ".")]
    pub path: std::path::PathBuf,

    /// Maximum number of files to analyze
    #[arg(short, long, default_value = "5000")]
    pub max_files: usize,

    /// Maximum git commits to analyze for time-travel
    #[arg(long, default_value = "500")]
    pub max_commits: usize,

    /// Output JSON graph data instead of TUI
    #[arg(long)]
    pub json: bool,

    /// Skip the TUI and just print stats
    #[arg(long)]
    pub stats: bool,

    /// Disable git integration
    #[arg(long)]
    pub no_git: bool,

    /// Disable file watcher (live reload)
    #[arg(long)]
    pub no_watch: bool,
}
