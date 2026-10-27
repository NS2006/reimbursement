import { useEffect, useRef, useState, type PointerEvent } from "react";
import { dateLocale } from "../app/i18n";
import "../styles/components/PriceStepChart.css";

// A price over time as steps (a price holds until the next one starts), in one colour: the line, a light wash under
// it, a dot where each price starts, the last price written at the end. An announced price (from a later day) is
// drawn dashed. Hovering anywhere (or focusing a dot) shows the price that applied on that day; the dialog's table
// lists the same prices, so nothing is only in the tooltip.

export interface PriceStep {
  key: string | number;
  /** Day numbers (days since 01-01-1970): from the first day to the day the next price starts (excluded). */
  from: number;
  to: number;
  /** null: no price on those days (not listed): a gap in the line. */
  price: number | null;
  /** Announced for a later day. */
  upcoming: boolean;
  /** "Rp 15.950" */
  valueText: string;
  /** "02-09-2026 – 30-09-2026" */
  rangeText: string;
}

interface PriceStepChartProps {
  /** Oldest first, each from where the one before ends. */
  steps: PriceStep[];
  /** Today's day number: a thin line marks it. */
  today: number;
  todayLabel: string;
  /** What the chart shows, for screen readers. */
  label: string;
  className?: string;
}

const HEIGHT = 220;
const MARGIN = { top: 24, right: 92, bottom: 30, left: 60 };
const DAY_MS = 86_400_000;
const number = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });

/** About `count` round values covering min..max (steps of 1, 2 or 5 times a power of ten). */
function niceTicks(min: number, max: number, count: number): number[] {
  const span = Math.max(max - min, 1);
  const raw = span / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((factor) => factor * power).find((candidate) => candidate >= raw) ?? raw;
  const ticks: number[] = [];
  for (let value = Math.floor(min / step) * step; value <= Math.ceil(max / step) * step + step / 2; value += step) {
    ticks.push(value);
  }
  return ticks;
}

/** The first day of each month from `from` to `to`, at most `max` of them (every other one, ... when there are more). */
function monthTicks(from: number, to: number, max: number): number[] {
  const months: number[] = [];
  const start = new Date(from * DAY_MS);
  for (let month = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1)); ; ) {
    const day = month.getTime() / DAY_MS;
    if (day > to) break;
    months.push(day);
    month = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + 1, 1));
  }
  const every = Math.ceil(months.length / max);
  return months.filter((_, index) => index % every === 0);
}

export function PriceStepChart({ steps, today, todayLabel, label, className = "" }: PriceStepChartProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [active, setActive] = useState<{ step: PriceStep; x: number } | null>(null);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, []);

  const priced = steps.filter((step) => step.price !== null);
  if (steps.length === 0 || priced.length === 0) return null;

  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const start = steps[0].from;
  const end = steps[steps.length - 1].to;
  const x = (day: number) => MARGIN.left + ((day - start) / Math.max(end - start, 1)) * plotWidth;

  const values = priced.map((step) => step.price as number);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const padding = Math.max((high - low) * 0.15, high * 0.02);
  const ticks = niceTicks(low - padding, high + padding, 5);
  const yMin = ticks[0];
  const yMax = ticks[ticks.length - 1];
  const y = (price: number) => MARGIN.top + ((yMax - price) / Math.max(yMax - yMin, 1)) * plotHeight;
  const bottom = MARGIN.top + plotHeight;

  // The line: a step goes on from the one before it with a vertical jump; a gap (no price) starts a new piece.
  let solid = "";
  let dashed = "";
  steps.forEach((step, index) => {
    if (step.price === null) return;
    const before = index > 0 ? steps[index - 1].price : null;
    const join = before !== null ? `M${x(step.from)},${y(before)} V${y(step.price)}` : `M${x(step.from)},${y(step.price)}`;
    const piece = `${join} H${x(step.to)} `;
    if (step.upcoming) dashed += piece;
    else solid += piece;
  });
  const last = priced[priced.length - 1];
  const months = monthTicks(start, end, Math.max(2, Math.floor(plotWidth / 90)));
  const monthName = new Intl.DateTimeFormat(dateLocale(), { month: "short", year: "numeric", timeZone: "UTC" });

  function onPointerMove(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!box) return;
    const pointerX = Math.min(Math.max(event.clientX - box.left, MARGIN.left), MARGIN.left + plotWidth);
    const day = start + ((pointerX - MARGIN.left) / plotWidth) * (end - start);
    const step = steps.find((item) => day >= item.from && day < item.to) ?? steps[steps.length - 1];
    setActive({ step, x: pointerX });
  }

  const tooltipLeft = active ? Math.min(Math.max(active.x, 90), width - 90) : 0;
  const tooltipTop = active?.step.price != null ? y(active.step.price) : MARGIN.top + plotHeight / 2;

  return (
    <div ref={wrapperRef} className={`price-chart ${className}`.trim()}>
      <svg width={width} height={HEIGHT} role="img" aria-label={label} className="price-chart__svg">
        {/* Grid: the prices on the left, the months below */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="price-chart__grid" x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} />
            <text className="price-chart__tick" x={MARGIN.left - 8} y={y(tick)} dy="0.32em" textAnchor="end">
              {number.format(tick)}
            </text>
          </g>
        ))}
        {months.map((day) => (
          <text key={day} className="price-chart__tick" x={x(day)} y={bottom + 18} textAnchor="middle">
            {monthName.format(new Date(day * DAY_MS))}
          </text>
        ))}

        {/* Today */}
        {today >= start && today <= end ? (
          <g className="price-chart__today">
            <line x1={x(today)} x2={x(today)} y1={MARGIN.top - 6} y2={bottom} />
            <text x={x(today)} y={MARGIN.top - 10} textAnchor="middle">
              {todayLabel}
            </text>
          </g>
        ) : null}

        {/* A light wash under the prices that applied, then the line */}
        {steps.map((step) =>
          step.price === null || step.upcoming ? null : (
            <rect
              key={`wash-${step.key}`}
              className="price-chart__wash"
              x={x(step.from)}
              y={y(step.price)}
              width={Math.max(0, x(step.to) - x(step.from))}
              height={Math.max(0, bottom - y(step.price))}
            />
          ),
        )}
        <path className="price-chart__line" d={solid} />
        {dashed ? <path className="price-chart__line price-chart__line--upcoming" d={dashed} /> : null}

        {/* The pointer: a hairline at the day, over the whole plot */}
        {active ? <line className="price-chart__crosshair" x1={active.x} x2={active.x} y1={MARGIN.top} y2={bottom} /> : null}
        <rect
          className="price-chart__hit"
          x={MARGIN.left}
          y={MARGIN.top}
          width={plotWidth}
          height={plotHeight}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setActive(null)}
        />

        {/* A dot where each price starts (focusable: the same tooltip as hovering) */}
        {steps.map((step) =>
          step.price === null ? null : (
            <g
              key={`dot-${step.key}`}
              className="price-chart__point"
              tabIndex={0}
              role="img"
              aria-label={`${step.valueText}, ${step.rangeText}`}
              onFocus={() => setActive({ step, x: x(step.from) })}
              onBlur={() => setActive(null)}
              onPointerEnter={() => setActive({ step, x: x(step.from) })}
              onPointerLeave={() => setActive(null)}
            >
              <circle className="price-chart__target" cx={x(step.from)} cy={y(step.price)} r={12} />
              <circle
                className={`price-chart__dot ${step.upcoming ? "price-chart__dot--upcoming" : ""}`.trim()}
                cx={x(step.from)}
                cy={y(step.price)}
                r={4.5}
              />
            </g>
          ),
        )}

        {/* The last price, written at the end of the line */}
        {last.price !== null ? (
          <text className="price-chart__end" x={x(last.to) + 8} y={y(last.price)} dy="0.32em">
            {last.valueText}
          </text>
        ) : null}
      </svg>

      {active ? (
        <div className="price-chart__tooltip" style={{ left: tooltipLeft, top: tooltipTop }} role="presentation">
          <strong>{active.step.valueText}</strong>
          <span>{active.step.rangeText}</span>
        </div>
      ) : null}
    </div>
  );
}
