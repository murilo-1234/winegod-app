export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  wines?: WineEmbed[];
  quickButtons?: string[];
  imagePreviews?: string[];
}

export interface WineData {
  id: number;
  nome: string;
  produtor: string;
  safra: string;
  tipo: string;
  pais: string;
  regiao: string;
  uvas: string[];
  nota: number;
  nota_tipo: "verified" | "estimated";
  score: number;
  termos: string[];
  preco_min: number | null;
  preco_max: number | null;
  moeda: string;
  imagem_url: string | null;
  total_fontes: number;
}

export interface WineCardData {
  type: "wine_card";
  wine: WineData;
}

export interface WineComparisonData {
  type: "wine_comparison";
  wines: WineData[];
}

export type WineEmbed = WineCardData | WineComparisonData;
