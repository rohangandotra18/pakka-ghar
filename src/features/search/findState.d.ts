export type Place = { name: string; lat: number; lng: number };
export type Bounds = { west: number; south: number; east: number; north: number };
export type Gender = 'Boys' | 'Girls' | 'Co-ed';
export type RoomKind = 'single' | 'double' | 'triple';
export type Filters = { gender?: Gender; rent?: number; kind?: RoomKind };
export type ListingsQuery = {
  lat?: number; lng?: number; radius_km?: number; bbox?: string;
  gender?: Gender; max_rent_paise?: number; kind?: RoomKind;
};
export type AreaOffer = 'none' | 'search' | 'zoom';

export const RADIUS_KM: number;
export const MAX_BBOX_SPAN: number;
export function round5(n: number): number;
export function roundBounds(b: Bounds): Bounds;
export function bboxString(b: Bounds): string;
export function bboxTooLarge(b: Bounds): boolean;
export function boundsDiffer(a: Bounds | null | undefined, b: Bounds | null | undefined): boolean;
export function buildListingsQuery(s: { place: Place; area: Bounds | null; filters: Filters }): ListingsQuery;
export function countFilters(f: Filters): number;
export function areaOffer(region: { bounds: Bounds; byUser: boolean } | null | undefined, searched: Bounds | null): AreaOffer;
export function placeSubtitle(p: { kind: string; city: string }): string;
export function samePlace(a: { name: string }, b: { name: string }): boolean;
export function placeChips<P extends Place>(popular: P[] | undefined, fallback: P[], chosen: P, max?: number): P[];
