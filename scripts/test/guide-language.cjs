// Navigation behavior without a browser or a writable localStorage requirement.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(new URL('../../docs/assets/language.js', 'file://' + __filename), 'utf8');
function visit({path='',page='',languages=['ja-JP'],saved=null,query='',blocked=false}={}) {
  const url = new URL('https://example.test/steamac-lite/'+path+query);
  let redirected = null;
  const values = new Map(saved ? [['steamac-guide-language',saved]] : []);
  const links = [{dataset:{language:'en'},href:'https://example.test/steamac-lite/en/'+(page==='support'?'support/':''),addEventListener(_,handler){this.click=handler;}}];
  const context = {
    URL,URLSearchParams,
    navigator:{languages},
    location:{pathname:url.pathname,search:url.search,hash:url.hash,replace:target=>{redirected=target;}},
    localStorage:{getItem:key=>{if(blocked)throw Error('blocked');return values.get(key);},setItem:(key,value)=>{if(blocked)throw Error('blocked');values.set(key,value);}},
    document:{currentScript:{src:'https://example.test/steamac-lite/assets/language.js'},
      documentElement:{lang:path.startsWith('zh-CN')?'zh-Hans':path.split('/')[0]||'ja',dataset:{page}},
      addEventListener:(_,handler)=>handler(),querySelectorAll:()=>links},
  };
  vm.runInNewContext(source,context);
  return {redirected,values,links};
}
for(const [language,path] of [['ja-JP',null],['en-US','en/'],['ko-KR','ko/'],['zh-CN','zh-CN/'],['zh-TW','zh-CN/']]) {
  assert.equal(visit({languages:[language]}).redirected,path&&'https://example.test/steamac-lite/'+path);
}
assert.equal(visit({languages:['fr-FR','ko-KR']}).redirected,'https://example.test/steamac-lite/ko/');
assert.equal(visit({languages:['fr-FR']}).redirected,'https://example.test/steamac-lite/en/');
assert.equal(visit({languages:['en-US'],saved:'ja'}).redirected,null);
const explicit=visit({languages:['en-US'],saved:'ko',query:'?lang=ja'});
assert.equal(explicit.redirected,null);
assert.equal(explicit.values.get('steamac-guide-language'),'ja');
assert.equal(visit({path:'ko/',saved:'ja'}).redirected,null);
assert.equal(visit({path:'ko/',saved:'ja'}).values.get('steamac-guide-language'),'ko');
assert.equal(visit({blocked:true,languages:['en-US']}).redirected,'https://example.test/steamac-lite/en/');
assert.equal(visit({blocked:true,query:'?lang=ja',languages:['en-US']}).redirected,null);
const anchor=visit({query:'?lang=ja#faq'});
anchor.links[0].click({});
assert.equal(anchor.links[0].href,'https://example.test/steamac-lite/en/#faq');
assert.equal(anchor.values.get('steamac-guide-language'),'en');
assert.equal(visit({path:'support/',page:'support',languages:['en-US']}).redirected,'https://example.test/steamac-lite/en/support/');
assert.equal(visit({path:'support/',page:'support',languages:['ko-KR'],query:'?lang=ja'}).redirected,null);
assert.equal(visit({path:'support/',page:'support',languages:['ko-KR'],saved:'zh-CN'}).redirected,'https://example.test/steamac-lite/zh-CN/support/');
assert.equal(visit({path:'en/support/',page:'support',saved:'ja'}).redirected,null);
assert.equal(visit({path:'ko/support/',page:'support',saved:'en'}).values.get('steamac-guide-language'),'ko');
assert.equal(visit({path:'support/',page:'support',blocked:true,languages:['en-US'],query:'#microphone'}).redirected,'https://example.test/steamac-lite/en/support/#microphone');
const supportAnchor=visit({path:'support/',page:'support',query:'?lang=ja#microphone'});
supportAnchor.links[0].click({});
assert.equal(supportAnchor.links[0].href,'https://example.test/steamac-lite/en/support/#microphone');
console.log('Guide and support language routing: preferences, explicit URLs, blocked storage and section links passed.');
