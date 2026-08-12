/**
 * BrokenLinkBrief portfolio dashboard — TypeScript client example.
 *
 * Mirrors the dashboard's portfolio section (see docs/portfolio-dashboard.md):
 *   - GET /api/portfolio            -> { summary, projects }
 *   - GET /api/portfolio/summary?days= -> { summary, trend }
 *   - Client-side CSV export of the project rows.
 *
 * Run:
 *   npx tsc --noEmit --strict --target es2020 --module es2020 --lib es2020,dom,es2021 examples/portfolio-example.ts
 *
 * The API is auth-gated when BROKENLINKBRIEF_SCAN_TOKEN is set; pass the token
 * as a query parameter or Authorization: Bearer header, exactly like the
 * dashboard does.
 */

/** One project's aggregated row (mirrors PortfolioProjectRow). */
export interface PortfolioProjectRow {
  project_id: string;
  project_name: string;
  total_links: number;
  broken_count: number;
  new_broken_count: number;
  open_findings: number;
  resolved_findings: number;
  last_scan_timestamp: string | null;
  last_scan_status: "completed" | "failed" | "never_run";
  pinned: boolean;
  archived: boolean;
}

/** Cross-project totals (mirrors PortfolioSummary). */
export interface PortfolioSummary {
  projects: number;
  scanned_projects: number;
  unscanned_projects: number;
  total_links: number;
  broken_count: number;
  new_broken_count: number;
  open_findings: number;
  resolved_findings: number;
  health_score: number;
  last_scan_timestamp: string | null;
}

/** One day of aggregated trend (mirrors PortfolioTrendPoint). */
export interface PortfolioTrendPoint {
  date: string; // "YYYY-MM-DD"
  total_links: number;
  broken_count: number;
}

export interface PortfolioPayload {
  summary: PortfolioSummary;
  projects: PortfolioProjectRow[];
}

export interface PortfolioSummaryPayload {
  summary: PortfolioSummary;
  trend: PortfolioTrendPoint[];
}

function tokenQuery(token: string | undefined): string {
  return token ? `?token=${encodeURIComponent(token)}` : "";
}

/** Fetch the portfolio overview: summary cards + per-project rows. */
export async function fetchPortfolio(
  token?: string,
): Promise<PortfolioPayload> {
  const res = await fetch(`/api/portfolio${tokenQuery(token)}`);
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as PortfolioPayload;
}

/** Fetch the aggregate summary plus the daily broken-link trend. */
export async function fetchPortfolioSummary(
  days: number,
  token?: string,
): Promise<PortfolioSummaryPayload> {
  const res = await fetch(
    `/api/portfolio/summary?days=${days}${tokenQuery(token)}`,
  );
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as PortfolioSummaryPayload;
}

/**
 * Build the same CSV the dashboard downloads (portfolio-export.csv).
 * Cells are RFC 4180 quoted; a leading spreadsheet formula trigger
 * (= + - @ tab CR) is neutralized with an apostrophe (CWE-1236).
 */
export function portfolioToCsv(rows: PortfolioProjectRow[]): string {
  const header =
    "project_name,total_links,broken_count,open_findings,resolved_findings,last_scan_timestamp";
  const escapeCell = (value: unknown): string => {
    let text = value === null || value === undefined ? "" : String(value);
    if (/^[=+@\t\r-]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  };
  const lines = rows.map((p) =>
    [
      p.project_name,
      p.total_links,
      p.broken_count,
      p.open_findings,
      p.resolved_findings,
      p.last_scan_timestamp ?? "",
    ]
      .map(escapeCell)
      .join(","),
  );
  return [header, ...lines].join("\n") + "\n";
}

/**
 * Minimal Node runtime accessor that keeps the example type-checkable without
 * @types/node: `process` is only referenced via globalThis so the file also
 * type-checks in a browser context.
 */
declare const process: {
  env: Record<string, string | undefined>;
  argv: string[];
  exitCode?: number;
};

/** Demo: print the portfolio overview and a CSV export (Node 18+ has fetch). */
async function main(): Promise<void> {
  const token = process.env.BROKENLINKBRIEF_SCAN_TOKEN;
  const { summary, projects } = await fetchPortfolio(token);

  console.log(
    `Portfolio: ${summary.scanned_projects}/${summary.projects} projects scanned, ` +
      `${summary.broken_count} broken of ${summary.total_links} links, ` +
      `health ${summary.health_score}/100`,
  );

  const { trend } = await fetchPortfolioSummary(30, token);
  if (trend.length) {
    const last = trend[trend.length - 1];
    console.log(
      `Latest trend point (${last.date}): ${last.total_links} links, ` +
        `${last.broken_count} broken`,
    );
  }

  console.log("\nCSV export (portfolio-export.csv):");
  console.log(portfolioToCsv(projects));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err: unknown) => {
    console.error(err instanceof Error ? err.message : err);
    process.exitCode = 1;
  });
}
