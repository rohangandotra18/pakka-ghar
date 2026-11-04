/* Sample data for the prototype. Replace with the API once the backend exists. */
export const TARIFF = 7.25; // ₹ per unit, never above the DISCOM tariff

export type Gender = 'Boys' | 'Girls' | 'Co-ed';
export type PG = {
  id: string; name: string; gender: Gender; area: string; rent: number; free: number;
  meals: string; rating: number; stays: number; hot?: boolean; watching?: number; lat: number; lng: number;
};
export const PGS: PG[] = [
  { id: 'sidhu', name: 'Sidhu Boys PG', gender: 'Boys', area: 'Sector 15', rent: 9000, free: 1, meals: '3 meals', rating: 4.6, stays: 38, hot: true, watching: 14, lat: 30.7543, lng: 76.7713 },
  { id: 'pgiview', name: 'PGI View Residency', gender: 'Co-ed', area: 'Sector 11', rent: 11000, free: 3, meals: '2 meals', rating: 4.4, stays: 21, lat: 30.7612, lng: 76.779 },
  { id: 'gurnoor', name: 'Gurnoor Girls PG', gender: 'Girls', area: 'Sector 15', rent: 10000, free: 1, meals: '3 meals', rating: 4.8, stays: 52, hot: true, watching: 9, lat: 30.7509, lng: 76.774 },
  { id: 's24', name: "Sector 24 Working Women's PG", gender: 'Girls', area: 'Sector 24', rent: 9500, free: 2, meals: '2 meals', rating: 4.3, stays: 17, lat: 30.7451, lng: 76.7616 },
];

export type Resident = { name: string; room: string; rent: number; autopay: boolean; paid: boolean; police: 'Verified' | 'Submitted' | 'Not started'; kwh: number; since: string; rating?: number };
export const RESIDENTS: Resident[] = [
  { name: 'Aman Verma', room: '101', rent: 9000, autopay: true, paid: true, police: 'Verified', kwh: 86, since: 'Aug 2026', rating: 4.8 },
  { name: 'Rohit Saini', room: '101', rent: 9000, autopay: false, paid: false, police: 'Verified', kwh: 112, since: 'Jul 2026', rating: 4.5 },
  { name: 'Harsh Gupta', room: '102', rent: 9000, autopay: true, paid: true, police: 'Submitted', kwh: 64, since: 'Sep 2026' },
  { name: 'Nikhil Rana', room: '103', rent: 7500, autopay: false, paid: false, police: 'Not started', kwh: 58, since: 'Oct 2026' },
  { name: 'Yash Thakur', room: '103', rent: 7500, autopay: true, paid: true, police: 'Verified', kwh: 61, since: 'Jun 2025', rating: 4.9 },
];
export const PAST_RESIDENTS = [
  { name: 'Kartik Mehra', room: '102', from: 'Jul 2024', to: 'May 2025', rating: 4.6, deposit: 'Returned in 3 days' },
  { name: 'Sahil Bansal', room: '201', from: 'Aug 2023', to: 'Jun 2025', rating: 4.9, deposit: 'Returned in 2 days' },
  { name: 'Varun Kohli', room: '103', from: 'Jan 2025', to: 'Apr 2025', rating: 3.2, deposit: '₹2,000 kept for a broken chair' },
];
export type Offer = { name: string; amount: number; months: number; moveIn: string; verified: boolean; score?: number; pastStays: number };
export const OFFERS: Offer[] = [
  { name: 'Aditya Rawal', amount: 10200, months: 6, moveIn: '5 Dec', verified: true, score: 4.4, pastStays: 1 },
  { name: 'Vivek Sharma', amount: 9900, months: 11, moveIn: '1 Dec', verified: true, score: 4.7, pastStays: 2 },
  { name: 'Ishaan Malik', amount: 9700, months: 9, moveIn: '10 Dec', verified: false, pastStays: 0 },
  { name: 'Lakshay Bhalla', amount: 9450, months: 11, moveIn: '1 Dec', verified: true, pastStays: 0 },
];
export type Req = { id: string; who: string; room: string; cat: string; text: string; status: 'Raised' | 'Assigned' | 'Fixed' | 'Confirmed'; at: string; to?: string };
export const OWNER_REQUESTS: Req[] = [
  { id: 'R-218', who: 'Rohit Saini', room: '101', cat: 'Electrical', text: 'Ceiling fan makes a grinding noise', status: 'Assigned', at: 'Today 9:10', to: 'Gurmeet (electrician)' },
  { id: 'R-217', who: 'Harsh Gupta', room: '102', cat: 'Wi-Fi', text: 'Wi-Fi drops every evening', status: 'Raised', at: 'Yesterday' },
  { id: 'R-209', who: 'Yash Thakur', room: '103', cat: 'Plumbing', text: 'Geyser not heating', status: 'Fixed', at: '3 Nov', to: 'Raju (plumber)' },
];
export const MY_HISTORY: { name: string; area: string; from: string; to: string; rent: number; current?: boolean; rated?: number; deposit?: string }[] = [
  { name: 'Shiv Shakti PG', area: 'Kharar', from: 'Jul 2025', to: 'Jul 2026', rent: 6500, rated: 4, deposit: 'Deposit returned in 4 days' },
  { name: 'Hostel A-Block', area: 'Bathinda', from: 'Jul 2023', to: 'May 2025', rent: 4000, rated: 5, deposit: 'Deposit returned' },
];
export const DAILY_KWH = [2.1, 2.6, 2.4, 3.1, 2.8, 1.9, 2.2, 3.4, 3.0, 2.7, 2.9, 3.3, 2.5, 2.0];
export const REQUEST_CATEGORIES = ['Electrical', 'Plumbing', 'Wi-Fi', 'Cleaning', 'Furniture', 'Listing issue', 'Asked to pay in cash'];
