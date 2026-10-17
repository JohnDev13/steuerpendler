import { strings } from './strings';
const app = document.querySelector<HTMLDivElement>('#app')!;
const main = document.createElement('main');
const title = document.createElement('h1'); title.textContent = strings.appName;
const status = document.createElement('p'); status.dataset.testid = 'release-status'; status.textContent = strings.preview;
const intro = document.createElement('p'); intro.textContent = strings.intro;
const pending = document.createElement('p'); pending.textContent = strings.pending;
main.append(title, status, intro, pending); app.replaceChildren(main);
