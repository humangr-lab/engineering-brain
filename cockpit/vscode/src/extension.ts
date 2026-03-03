import * as vscode from "vscode";
import { OntologyMapPanel } from "./panel";

let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand("ontology-map.open", () => {
      OntologyMapPanel.createOrShow(context);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ontology-map.refresh", () => {
      if (OntologyMapPanel.currentPanel) {
        OntologyMapPanel.currentPanel.refresh();
      } else {
        OntologyMapPanel.createOrShow(context);
      }
    }),
  );

  // Status bar item
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    50,
  );
  statusBarItem.command = "ontology-map.open";
  statusBarItem.text = "$(symbol-structure) Ontology Map";
  statusBarItem.tooltip = "Open Architecture View (Cmd+Shift+M)";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // Listen for file saves to trigger refresh if panel is open
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(() => {
      if (OntologyMapPanel.currentPanel) {
        OntologyMapPanel.currentPanel.onFileSaved();
      }
    }),
  );
}

export function deactivate() {
  statusBarItem?.dispose();
}
