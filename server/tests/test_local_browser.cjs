// Run with PLAYWRIGHT_MODULE and STUDIO_TEST_PYTHON when not on PATH.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const assert=require('node:assert/strict');
(async()=>{
 const child=spawn(process.env.STUDIO_TEST_PYTHON||'python3',['-m','server.tests.local_browser_fixture'],{stdio:['pipe','pipe','inherit']});
 let browser;
 try{
 const [line]=await once(child.stdout,'data');const {port}=JSON.parse(line.toString());
 const base='http://localhost:'+port;
 browser=await chromium.launch({headless:true});
 const context=await browser.newContext();
 await context.grantPermissions(['local-network-access'],{origin:'https://viewer.example'});
 const page=await context.newPage();const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 let remoteWrites=0;
 await page.route('https://viewer.example/**',async route=>{
  const request=route.request();if(request.method()==='POST')remoteWrites++;
  const u=new URL(request.url());
  const response=await context.request.fetch(base+u.pathname+u.search,{method:request.method(),headers:{Host:'viewer.example','Cf-Access-Jwt-Assertion':'browser-test-owner'}});
  await route.fulfill({response});
 });
 await page.goto('https://viewer.example/');
 await page.getByText('Connected to this recording Mac. Choose a production to open its room.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Open singing room'}).click();
 const sing=page.frameLocator('iframe');
 await sing.getByRole('heading',{name:'Singing Studio · Test'}).waitFor();
 await sing.locator('#stage').filter({hasText:'idle'}).waitFor();
 await sing.locator('#go').click();
 await sing.locator('#stage').filter({hasText:'rolling'}).waitFor();
 await sing.locator('#go').click();
 await sing.locator('#stage').filter({hasText:'singing'}).waitFor();
 await sing.locator('#go').click();
 await sing.getByRole('button',{name:'Stop',exact:true}).waitFor();
 await sing.locator('#go').click();
 await sing.getByRole('button',{name:'Load playback'}).click();
 await sing.locator('audio[src^="blob:"]').waitFor();
 await page.screenshot({path:'/tmp/st17-singing.png',fullPage:true});
 await page.getByRole('button',{name:'Close room',exact:true}).click();
 await page.locator('iframe').waitFor({state:'detached'});
 await page.getByRole('button',{name:'Open talking room'}).click();
 const talk=page.frameLocator('iframe');
 await talk.locator('#partsel').waitFor();
 await talk.locator('#reh').check();
 await page.screenshot({path:'/tmp/st17-talking.png',fullPage:true});
 await page.getByRole('button',{name:'Close room',exact:true}).click();
 await page.locator('iframe').waitFor({state:'detached'});
 assert.equal(remoteWrites,0,'recording commands must not use the public route');
 assert.deepEqual(errors,[]);
 // A different computer (local probe unavailable) stays a viewer.
 await page.route(base+'/**',route=>route.abort());
 await page.reload();
 await page.getByText(/Viewing only: could not connect/).waitFor();
 assert.equal(await page.getByRole('button',{name:'Open singing room'}).isDisabled(),true);
 await page.screenshot({path:'/tmp/st17-remote.png',fullPage:true});
 await page.unroute(base+'/**');
 // The direct localhost entry works without cross-origin configuration.
 await page.goto(base+'/song/test');
 await page.getByText('Connected to this recording Mac. Choose a production to open its room.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Open singing room'}).click();
 await page.frameLocator('iframe').getByRole('heading',{name:'Singing Studio · Test'}).waitFor();
 await page.getByRole('button',{name:'Close room',exact:true}).click();
 console.log('PASS: public URL direct singing/talking, remote fallback, localhost entry; no public writes or browser errors');
 }finally{if(browser)await browser.close();child.stdin.end();await once(child,'exit');}
})().catch(e=>{console.error(e);process.exitCode=1;});
