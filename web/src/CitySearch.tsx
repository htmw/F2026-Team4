import { useEffect, useId, useRef, useState } from "react";

import { currencyForCountry } from "./currency";

export interface CitySuggestion {
  label: string;
  value: string;
  // The city's local currency, from Photon's country code (undefined if unknown).
  currency?: string;
}

interface Props {
  value: string;
  onType: (text: string) => void;
  onSelect: (city: CitySuggestion) => void;
  error?: string;
}

// Destination input with live city suggestions from Photon (photon.komoot.io), an
// OpenStreetMap search built for autocomplete. Do not call Nominatim from the browser: its
// usage policy forbids client-side autocomplete. Suggestions are a convenience only; typing a
// city name by hand still works.
//
// Built as an ARIA 1.2 combobox: the input owns a listbox outside its label, the highlighted
// option is announced through aria-activedescendant, and options are not nested buttons.
export function CitySearch({ value, onType, onSelect, error }: Props) {
  const id = useId();
  const inputId = `${id}-input`;
  const listId = `${id}-list`;
  const errorId = `${id}-error`;
  const [suggestions, setSuggestions] = useState<CitySuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const seqRef = useRef(0);
  const hasTyped = useRef(false);
  const justSelected = useRef(false);

  useEffect(() => {
    const query = value.trim();
    if (!hasTyped.current || justSelected.current) {
      justSelected.current = false;
      setSearching(false);
      setOpen(false);
      return;
    }
    if (query.length < 2) {
      setSuggestions([]);
      setSearching(false);
      setOpen(false);
      return;
    }
    const seq = ++seqRef.current;
    setSearching(true);
    setOpen(true);
    const timer = window.setTimeout(async () => {
      try {
        const resp = await fetch(
          `https://photon.komoot.io/api/?q=${encodeURIComponent(query)}&limit=10&lang=en`,
        );
        if (!resp.ok || seq !== seqRef.current) return;
        const data = (await resp.json()) as {
          features: Array<{
            properties: { name?: string; country?: string; osm_value?: string; countrycode?: string };
          }>;
        };
        const cities: CitySuggestion[] = [];
        for (const feature of data.features) {
          const { name = "", country = "", osm_value = "", countrycode } = feature.properties;
          if (!["city", "town", "village", "municipality"].includes(osm_value)) continue;
          const label = country ? `${name}, ${country}` : name;
          // Photon can return the same city twice (a node and an area); show it once.
          if (cities.some((city) => city.value === label)) continue;
          cities.push({ label, value: label, currency: currencyForCountry(countrycode) });
          if (cities.length === 5) break;
        }
        setSuggestions(cities);
        setHighlighted(-1);
      } catch {
        // No suggestions on network failure; the typed text still works.
      } finally {
        if (seq === seqRef.current) setSearching(false);
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [value]);

  function select(city: CitySuggestion) {
    seqRef.current += 1;
    justSelected.current = true;
    setSuggestions([]);
    setOpen(false);
    setHighlighted(-1);
    onSelect(city);
  }

  const expanded = open && (searching || suggestions.length > 0 || value.trim().length >= 2);
  const activeId = highlighted >= 0 ? `${id}-opt-${highlighted}` : undefined;
  const describedBy = error ? errorId : undefined;

  return (
    <div className="field city-search">
      <label htmlFor={inputId}>Destination</label>
      <input
        id={inputId}
        type="text"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-activedescendant={expanded ? activeId : undefined}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(event) => {
          hasTyped.current = true;
          onType(event.target.value);
        }}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true);
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && suggestions.length > 0) {
            event.preventDefault();
            setOpen(true);
            setHighlighted((prev) => (prev + 1) % suggestions.length);
          } else if (event.key === "ArrowUp" && suggestions.length > 0) {
            event.preventDefault();
            setOpen(true);
            setHighlighted((prev) => (prev - 1 + suggestions.length) % suggestions.length);
          } else if (event.key === "Enter" && expanded && highlighted >= 0 && suggestions[highlighted]) {
            event.preventDefault();
            select(suggestions[highlighted]);
          } else if (event.key === "Escape" && expanded) {
            event.preventDefault();
            setOpen(false);
          }
        }}
      />
      <ul id={listId} role="listbox" aria-label="Matching cities" className="city-options" hidden={!expanded}>
        {suggestions.map((city, index) => (
          <li
            key={city.value}
            id={`${id}-opt-${index}`}
            role="option"
            aria-selected={index === highlighted}
            className={index === highlighted ? "is-highlighted" : undefined}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => select(city)}
          >
            {city.label}
          </li>
        ))}
      </ul>
      {expanded && suggestions.length === 0 && (
        <p className="city-options-note" role="status">
          {searching ? "Searching…" : "No matching cities. You can still type the name."}
        </p>
      )}
      {error && (
        <p id={errorId} className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
