import type {PetPlace} from '../../api/client';
export const cuisineColors: Record<string,string> = {
  '咖啡／輕食':'#8b5a2b','中式':'#cf3f45','港式':'#e17422','日式':'#d24e8d',
  '韓式':'#8854b6','西式':'#3266ba','意式／薄餅':'#34965e','泰式':'#b39108',
  '越式':'#008c85','甜品':'#b34ea8','素食':'#5b861d','法式':'#5964a5',
  '台式':'#9e482a','印度／中東':'#a56c0a','墨西哥／拉美':'#008cb7','海鮮':'#267fba',
  '酒吧／燒烤':'#713f67','其他餐廳':'#647660','未分類':'#8b9096',
};
export function cuisineColor(value: string) {return cuisineColors[value] || cuisineColors['未分類'];}
export function restaurantColor(place: PetPlace) {return cuisineColor(place.cuisines[0] || '未分類');}
