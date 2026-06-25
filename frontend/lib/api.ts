import { InvestigationResponse } from "./types";

export async function investigate(type: string, value: string): Promise<InvestigationResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  
  try {
    const response = await fetch(`${apiUrl}/investigate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ type, value }),
    });

    if (!response.ok) {
      throw new Error(`API returned status ${response.status}`);
    }

    const data: InvestigationResponse = await response.json();
    return data;
  } catch (error) {
    throw new Error("Could not reach VERTEX backend. Is it running on port 8000?");
  }
}
