/**
 * Two XYZ classes, named apart on screen (CLAUDE.md, Sales analytics):
 *   "Demand variability" (products pages): the CV of weekly units, how much volume moves.
 *   "Forecastability" (forecast pages): the CV of the champion's backtest errors, how far
 *   the forecasts missed. A regular festival peak is variable demand yet forecastable.
 */
export const FORECASTABILITY_TIP =
  "Forecastability: how much the forecast’s backtest errors varied (error CV), not how much demand varies.";

export const DEMAND_VARIABILITY_TIP =
  "Demand variability: how much weekly units vary (volume CV), not how well they can be forecast.";

export function ForecastabilityNote({ xBelow, yUpTo }: { xBelow: number; yUpTo: number }) {
  return (
    <p>
      <span className="font-medium text-fg">Forecastability</span> (X, Y, Z) comes from the
      backtest: the spread of the forecast’s errors relative to sales (error CV), X under {xBelow},
      Y up to {yUpTo}, Z above. It is not the products page’s demand variability, which measures how
      much the sales themselves move: a regular festival peak makes demand variable but can still be
      forecast well.
    </p>
  );
}
