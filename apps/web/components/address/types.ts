export type City = { id: string; ru: string; kk: string; lat: number; lon: number; radius: number; bbox: [number, number, number, number] };
export type Place = {
  name: string | null;
  label: string;
  kind: "complex" | "building" | "street" | "city" | "other";
  street: string | null;
  housenumber: string | null;
  city: string | null;
  lat: number;
  lon: number;
};
export type Picked = { label: string; city: string | null; place?: Place };
