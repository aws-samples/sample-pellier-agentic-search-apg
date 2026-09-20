import {expect,test} from '@playwright/test'
import fs from 'node:fs/promises'
import {createRequire} from 'node:module'
import type {AxeResults} from 'axe-core'
const require = createRequire(import.meta.url)
test.use({trace:'off',screenshot:'off',reducedMotion:'reduce'})
test('release accessibility and current public screenshots',async({page},testInfo)=>{
 test.setTimeout(180000)
 await page.emulateMedia({reducedMotion:'reduce'})
 expect(await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true)
 await page.addInitScript(()=>{sessionStorage.setItem('pellier-storefront-spotlight-seen','true');sessionStorage.setItem('observatory-spotlight-seen','true')})
 const findings: {route:string;width:number;violations:AxeResults['violations'];incomplete:string[]}[]=[]
 for(const width of [1920,1280,390]){
  await page.setViewportSize({width,height:900})
  for(const route of ['/','/signin','/observatory','/observatory/workbench','/observatory/govern/verification','/operator/clients/CUST-JESSICA']){
   await page.goto(route)
   await expect(page.getByRole('heading',{level:1}).first()).toBeVisible()
   await page.addScriptTag({path:require.resolve('axe-core/axe.min.js')})
   const result=await page.evaluate(async()=>await (window as unknown as {axe:typeof import('axe-core')}).axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}}))
   findings.push({route,width,violations:result.violations,incomplete:result.incomplete.map(v=>v.id)})
   await page.screenshot({path:testInfo.outputPath(`${route.replaceAll('/','_')||'home'}-${width}.png`),fullPage:true,animations:'disabled'})
  }
 }
 await fs.writeFile(testInfo.outputPath('accessibility.json'),JSON.stringify(findings,null,2))
 expect(findings.flatMap(f=>f.violations)).toEqual([])
})
