"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { compactNumber, formatNumber } from "@/lib/format";
import type { ChartSpec } from "@/lib/types";

const COLORS = ["#4f46e5", "#0d9488", "#d97706", "#e11d48", "#0284c7", "#7c3aed", "#65a30d", "#db2777"];
const axisStyle = { fontSize: 12, fill: "#64748b" };
const margin = { top: 8, right: 16, bottom: 28, left: 8 };

const tooltipFormatter = (value: unknown) => (typeof value === "number" ? formatNumber(value) : String(value));

function renderChart(spec: ChartSpec) {
  const xAxis = (
    <XAxis
      dataKey={spec.x_key}
      tick={axisStyle}
      tickLine={false}
      axisLine={{ stroke: "#cbd5e1" }}
      interval="preserveStartEnd"
      label={{ value: spec.x_label, position: "insideBottom", offset: -16, style: axisStyle }}
    />
  );
  const yAxis = (
    <YAxis
      tick={axisStyle}
      tickLine={false}
      axisLine={false}
      tickFormatter={compactNumber}
      width={64}
      label={{ value: spec.y_label, angle: -90, position: "insideLeft", offset: 4, style: { ...axisStyle, textAnchor: "middle" } }}
    />
  );
  const grid = <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />;
  const legend = spec.y_keys.length > 1 ? <Legend verticalAlign="top" height={28} iconType="circle" /> : null;

  if (spec.type === "line") {
    return (
      <LineChart data={spec.data} margin={margin}>
        {grid}
        {xAxis}
        {yAxis}
        <Tooltip formatter={tooltipFormatter} />
        {legend}
        {spec.y_keys.map((key, i) => (
          <Line isAnimationActive={false} key={key} type="monotone" dataKey={key} stroke={COLORS[i % COLORS.length]} strokeWidth={2.5} dot={spec.data.length <= 40} connectNulls />
        ))}
      </LineChart>
    );
  }
  if (spec.type === "pie") {
    return (
      <PieChart>
        <Pie isAnimationActive={false} data={spec.data} dataKey={spec.y_keys[0]} nameKey={spec.x_key} innerRadius="45%" outerRadius="80%" paddingAngle={2}>
          {spec.data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip formatter={tooltipFormatter} />
        <Legend verticalAlign="bottom" iconType="circle" />
      </PieChart>
    );
  }
  if (spec.type === "scatter") {
    return (
      <ScatterChart margin={margin}>
        {grid}
        <XAxis
          type="number"
          dataKey={spec.x_key}
          name={spec.x_label}
          tick={axisStyle}
          tickFormatter={compactNumber}
          label={{ value: spec.x_label, position: "insideBottom", offset: -16, style: axisStyle }}
        />
        <YAxis
          type="number"
          dataKey={spec.y_keys[0]}
          name={spec.y_label}
          tick={axisStyle}
          tickFormatter={compactNumber}
          width={64}
          label={{ value: spec.y_label, angle: -90, position: "insideLeft", offset: 4, style: { ...axisStyle, textAnchor: "middle" } }}
        />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={tooltipFormatter} />
        <Scatter isAnimationActive={false} data={spec.data} fill={COLORS[0]} fillOpacity={0.6} />
      </ScatterChart>
    );
  }
  const histogram = spec.type === "histogram";
  return (
    <BarChart data={spec.data} margin={margin} barCategoryGap={histogram ? 1 : "20%"}>
      {grid}
      {xAxis}
      {yAxis}
      <Tooltip formatter={tooltipFormatter} />
      {legend}
      {spec.y_keys.map((key, i) => (
        <Bar isAnimationActive={false} key={key} dataKey={key} fill={COLORS[i % COLORS.length]} radius={histogram ? 0 : [4, 4, 0, 0]} />
      ))}
    </BarChart>
  );
}

export default function ChartView({ spec, height = 320 }: { spec: ChartSpec; height?: number }) {
  return (
    <figure className="rounded-xl border border-slate-200 bg-white p-4">
      <figcaption className="mb-2 text-sm font-semibold text-slate-800">{spec.title}</figcaption>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {renderChart(spec)}
        </ResponsiveContainer>
      </div>
      {spec.note && <p className="mt-1 text-xs text-slate-500">{spec.note}</p>}
    </figure>
  );
}
