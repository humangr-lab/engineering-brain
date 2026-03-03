use clap::CommandFactory;
use clap_complete::{generate_to, Shell};

include!("src/cli.rs");

fn main() {
    let out_dir = std::path::PathBuf::from(
        std::env::var("OUT_DIR").unwrap_or_else(|_| "target".into()),
    );

    // Shell completions
    let completions_dir = out_dir.join("completions");
    std::fs::create_dir_all(&completions_dir).expect("failed to create completions dir");

    let mut cmd = Cli::command();
    for shell in [Shell::Bash, Shell::Zsh, Shell::Fish] {
        generate_to(shell, &mut cmd, "ontology-map", &completions_dir)
            .expect("failed to generate shell completions");
    }

    // Man page
    let man_dir = out_dir.join("man");
    std::fs::create_dir_all(&man_dir).expect("failed to create man dir");

    let man = clap_mangen::Man::new(Cli::command());
    let mut buf = Vec::new();
    man.render(&mut buf).expect("failed to render man page");
    std::fs::write(man_dir.join("ontology-map.1"), buf).expect("failed to write man page");
}
