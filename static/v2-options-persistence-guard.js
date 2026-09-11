(()=>{
  const seeds={
    garnitures:['Salade verte','Tomate','Oignons rouges','Oignons confits','Cornichons','Cheddar','Avocat','Œuf','Aubergines','Salade israélienne','Choux blanc','Choux rouge','Houmous','Tehina','Harissa','Ketchup','Mayonnaise','Moutarde','Sauce maison','Sauce barbecue','Sauce tartare','Sauce harissa-mayo','Moutarde au miel'],
    supplements:['Avocat','Bacon','Cheddar','Œuf','Oignons crispy','Plaque Cheddar','Steak 150 g','Frites Maison','Pita','Pita panée','Piment','Demi-baguette','Bassar','Bassar shawarma'],
    sauces:['Ketchup','Mayonnaise','Barbecue','Harissa maison','Harissa-mayo','Moutarde','Moutarde au miel','Tartare','Tehina','Houmous','Sauce américaine','Sauce maison','Sauce blanche à l’ail maison','Sauce chili douce','Sans sauces'],
    saucesSupp:['Barbecue','Harissa','Houmous'],
    cuisson:['Bleu','Saignant','À point','Bien cuit'],
    pain:['Baguette','Tacos','Pita','Pain kebab','Laffa','Pita panée','Tacos pané'],
    boissons:['Coca Cola','Coca zéro','Ice Tea pêche','Oasis Tropical','Sprite','Perrier','Évian','Schweppes agrumes','Caprisun','Boisson autre que Caprisun'],
    accompagnements:['Frites','Pate sauce tomate','Riz','Mini salade'],
    viandes:['Parguit','Poulet pané','Poulet crispy','Poulet grillé','Shawarma','Merguez','Kebab','Steak','Falafel'],
    poulet:['Poulet crispy','Poulet grillé','Poulet pané','Poulet parguit'],
    tender:['Classic Panure traditionnelle Maison','Crispy Panure extra croustillante Maison','Cheesy tradition maison, cœur cheddar']
  };
  const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const seedSets=Object.fromEntries(Object.entries(seeds).map(([k,v])=>[k,new Set(v.map(norm))]));
  const originalJson=Response.prototype.json;
  Response.prototype.json=async function(){
    const data=await originalJson.call(this);
    try{
      const url=String(this.url||'');
      if(!url.includes('/api/v2/catalog/admin')||!data?.data?.optionLists)return data;
      for(const [k,set] of Object.entries(seedSets)){
        if(!Object.prototype.hasOwnProperty.call(data.data.optionLists,k)||!Array.isArray(data.data.optionLists[k]))continue;
        const target=data.data.optionLists[k];
        data.data.optionLists[k]=new Proxy(target,{get(arr,prop,receiver){
          if(prop!=='push')return Reflect.get(arr,prop,receiver);
          return (...items)=>{
            let added=0;
            for(const item of items){
              const name=Array.isArray(item)?item[0]:item?.name;
              const n=norm(name);
              const exists=arr.some(x=>norm(Array.isArray(x)?x[0]:x?.name)===n);
              if(set.has(n)&&!exists)continue;
              Array.prototype.push.call(arr,item);added++;
            }
            return arr.length;
          };
        }});
      }
    }catch(e){console.error('BÉCHÉFAA V2 persistence guard:',e);}
    return data;
  };
})();