/**
 * PRISM Extension — Structural code analysis for AI agent loops.
 *
 * Registers a `prism` tool the LLM can call to get structural measurements
 * (parameter counts, nesting depth, dead code, cyclic imports) and Semgrep
 * findings (security, dev tooling, correctness) about the code it just wrote.
 *
 * Three speed tiers:
 *   --structure-only  → ~0.5s  (use every iteration)
 *   default           → ~10s   (use every few iterations)
 *   --community       → ~50s   (use for final audit)
 *
 * The tool uses async execution so the terminal stays responsive during scans.
 * Custom rendering provides a compact TUI display — full JSON is collapsed
 * by default, expand with Enter/Ctrl+E to inspect.
 *
 * Prerequisites:
 *   - PRISM CLI installed: `cd /home/k2/prism && uv sync`
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Text } from "@earendil-works/pi-tui";
import { Type } from "typebox";
import { exec } from "node:child_process";

// ── Configuration ──────────────────────────────────────────────────────

/** Path to the PRISM project directory (contains pyproject.toml).
 *  Override with PRISM_DIR environment variable. */
const PRISM_DIR = process.env.PRISM_DIR || "/home/k2/prism";

// ── Async shell helper ─────────────────────────────────────────────────

function runPrism(
	args: string,
	timeoutMs: number,
	signal?: AbortSignal,
): Promise<string> {
	return new Promise<string>((resolve, reject) => {
		const cmd = `uv run --directory ${PRISM_DIR} prism ${args}`;
		const child = exec(cmd, {
			encoding: "utf-8",
			timeout: timeoutMs,
			maxBuffer: 10 * 1024 * 1024,
		});

		if (signal) {
			signal.addEventListener("abort", () => {
				child.kill("SIGTERM");
				reject(new Error("PRISM scan cancelled"));
			});
		}

		let stdout = "";
		let stderr = "";

		child.stdout?.on("data", (chunk: string) => {
			stdout += chunk;
		});

		child.stderr?.on("data", (chunk: string) => {
			stderr += chunk;
		});

		child.on("error", (err: Error) => {
			reject(err);
		});

		child.on("close", (code: number | null) => {
			if (code === 0 || code === 1) {
				resolve(stdout);
			} else if (code === null) {
				reject(new Error("Process terminated"));
			} else {
				reject(
					new Error(
						`prism exited with code ${code}\n${stderr.split("\n").slice(-3).join("\n")}`,
					),
				);
			}
		});
	});
}

// ── Result parsing for TUI display ─────────────────────────────────────

interface PrismResult {
	measurements_count: number;
	measurements: Array<{
		metric: string;
		function: string;
		value: number;
	}>;
	semgrep_community?: unknown[];
	semgrep_curated?: unknown[];
	error?: string;
}

function parseResult(stdout: string): PrismResult | null {
	try {
		const parsed = JSON.parse(stdout) as PrismResult;
		if (parsed.error) return null;
		return parsed;
	} catch {
		return null;
	}
}

function summarizeMeasurements(result: PrismResult): string {
	const metrics = result.measurements ?? [];
	const counts: Record<string, number> = {};
	for (const m of metrics) {
		counts[m.metric] = (counts[m.metric] ?? 0) + 1;
	}

	const parts: string[] = [];
	for (const [metric, count] of Object.entries(counts)) {
		// Shorten metric names for display
		const short =
			metric === "parameter_count"
				? "params"
				: metric === "nesting_depth"
					? "nesting"
					: metric === "function_length"
						? "length"
						: metric === "dead_function"
							? "dead"
							: metric === "cyclomatic_complexity"
								? "cyclomatic"
								: metric === "cognitive_complexity"
									? "cognitive"
									: metric === "boolean_complexity"
										? "boolean"
										: metric === "error_handling_coverage"
											? "error_handling"
											: metric === "function_impurity"
												? "impurity"
												: metric.replace("_", " ");
		parts.push(`${count} ${short}`);
	}

	const semgrepCount =
		(result.semgrep_community?.length ?? 0) +
		(result.semgrep_curated?.length ?? 0);

	if (semgrepCount > 0) {
		parts.push(`${semgrepCount} semgrep`);
	}

	return parts.join(", ") || "all clear";
}

// ── Tool definition ────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "prism",
		label: "PRISM",
		description:
			"Analyze code and return structured measurements: parameter counts, " +
			"nesting depth, dead functions, cyclic imports, callers, and Semgrep " +
			"findings (security, dev tooling, correctness). " +
			"Results include cross-file caller context. " +
			"Use after writing/editing code to catch structural issues the model " +
			"might have missed.",
		promptSnippet:
			"Analyze code structure and return quantitative measurements " +
			"(params, nesting, dead code, cyclics, callers, Semgrep findings)",
		promptGuidelines: [
			"Use prism after writing or editing code to get structural measurements — parameter counts, nesting depth, dead code, cyclic imports, and caller context.",
			"prism's output includes a note that measurements are NOT exhaustive; use them as hints to start your own analysis, not as a complete diagnostic.",
			"prism has three speed tiers: --structure-only (~0.5s, use every iteration), default (~10s, use every few iterations), and --community (~50s, use for final audit).",
		],
		parameters: Type.Object({
			path: Type.String({
				description:
					"File or directory to analyze. Use a directory path for " +
					"project-wide analysis (includes cyclic imports across files).",
			}),
			mode: StringEnum(
				["structure-only", "default", "community"] as const,
			),
		}),
		async execute(
			_toolCallId,
			params: {
				path: string;
				mode: "structure-only" | "default" | "community";
			},
			signal: AbortSignal,
		) {
			const args: string[] = [];
			if (params.mode === "structure-only") args.push("--structure-only");
			if (params.mode === "community") args.push("--community");
			args.push(params.path);

			const timeouts: Record<string, number> = {
				"structure-only": 30_000,
				default: 60_000,
				community: 180_000,
			};

			try {
				const stdout = await runPrism(
					args.join(" "),
					timeouts[params.mode],
					signal,
				);

				return {
					content: [{ type: "text" as const, text: stdout }],
				};
			} catch (err: unknown) {
				const message =
					err instanceof Error ? err.message : "Unknown error";
				return {
					content: [
						{
							type: "text" as const,
							text:
								`PRISM error: ${message}\n\n` +
								"Make sure PRISM is installed:\n" +
								`  cd ${PRISM_DIR} && uv sync\n\n` +
								"Or check that semgrep is available:\n" +
								"  uv run semgrep --version",
						},
					],
				};
			}
		},

		// ── Custom TUI rendering ──────────────────────────────────────

		renderCall(
			args: { path: string; mode: string },
			theme: {
				fg: (style: string, text: string) => string;
				bold: (text: string) => string;
			},
		) {
			let text = theme.fg("toolTitle", theme.bold("prism "));
			text += theme.fg("accent", args.path);
			if (args.mode !== "default") {
				text += theme.fg("dim", ` (${args.mode})`);
			}
			return new Text(text, 0, 0);
		},

		renderResult(
			result: { content: Array<{ type: string; text: string }> },
			options: { expanded: boolean; isPartial: boolean },
			theme: {
				fg: (style: string, text: string) => string;
				bold: (text: string) => string;
			},
		) {
			if (options.isPartial) {
				return new Text(theme.fg("warning", "PRISM scanning..."), 0, 0);
			}

			const content = result.content[0];
			if (content?.type !== "text") {
				return new Text(theme.fg("error", "PRISM: no output"), 0, 0);
			}

			const parsed = parseResult(content.text);
			if (!parsed) {
				// Show error state compactly
				const lines = content.text.split("\n").slice(0, 3).join(" ");
				return new Text(theme.fg("error", `PRISM: ${lines}`), 0, 0);
			}

			const summary = summarizeMeasurements(parsed);
			let display = theme.fg("success", `prism: ${summary}`);

			if (options.expanded) {
				// Show full output when expanded
				const lines = content.text.split("\n");
				const maxLines = 40;
				const shown = lines.slice(0, maxLines);
				for (const line of shown) {
					display += `\n${theme.fg("dim", line)}`;
				}
				if (lines.length > maxLines) {
					display += `\n${theme.fg("muted", `... ${lines.length - maxLines} more lines`)}`;
				}
			}

			return new Text(display, 0, 0);
		},
	});
}
