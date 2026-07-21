import type {
  EngineeringReport,
  EquipmentScheduleRow,
  InstrumentScheduleRow,
  LineScheduleRow,
  RuleFinding,
  RuleSeverity,
} from "./types";

export type ReportTab = "equipment" | "lines" | "instruments" | "rules";
export type ReportRow = EquipmentScheduleRow | LineScheduleRow | InstrumentScheduleRow | RuleFinding;
export type SeverityFilter = RuleSeverity | "all";

export function reportTabCount(report: EngineeringReport, tab: ReportTab): number {
  if (tab === "rules") return report.findings.length;
  return report[tab].length;
}

export function reportRows(report: EngineeringReport, tab: ReportTab): ReportRow[] {
  return tab === "rules" ? report.findings : report[tab];
}

export function reportRowElementIds(row: ReportRow): string[] {
  if ("element_ids" in row) return row.element_ids;
  return [row.element_id];
}

function searchableText(row: ReportRow): string {
  return Object.values(row)
    .flatMap((value) => {
      if (typeof value === "string" || typeof value === "number") return [String(value)];
      if (Array.isArray(value)) return value.map(String);
      if (value && typeof value === "object") return [JSON.stringify(value)];
      return [];
    })
    .join(" ")
    .toLocaleLowerCase();
}

export function filterReportRows(
  report: EngineeringReport,
  tab: ReportTab,
  filter: string,
  severity: SeverityFilter = "all",
): ReportRow[] {
  const query = filter.trim().toLocaleLowerCase();
  return reportRows(report, tab).filter((row) => {
    if (tab === "rules" && severity !== "all" && "severity" in row && row.severity !== severity) return false;
    return !query || searchableText(row).includes(query);
  });
}

export const reportTabLabels: Record<ReportTab, string> = {
  equipment: "设备表",
  lines: "管线表",
  instruments: "仪表索引",
  rules: "规则检查",
};
