/*import {html, render} from 'lit-html';

import {streamService} from "../puzzle-pieces/stream.service";

import "./puzzle-time.css";


const tag = 'puzzle-time'
let lastInstanceId = 0;

interface TemplateData
{
  time: number;
}

class PmPuzzleTime extends HTMLElement
{
  static get _instanceID(): string{
    return `${tag} ${lastInstanceId++}`;
  }

  private instanceId: string;
  private puzzleId: string;
  private time: number;
  private startTime: number;

  constructor()
  {
    super();
    this.instanceId = PmPuzzleTime._instanceID;
    const puzzleId = this.attributes.getNamedItem('puzzle-id');
    this.puzzleId = puzzleId ? puzzleId.value : "";
    this.startTime = new Date().getTime();
    this.time = 0;

    streamService.subscribe('puzzle/time', this.timer.bind(this),
                             this.instanceId);

    streamService.connect(this.puzzleId);
    this.render();
  }

  template(data: TemplateData)
  {
    return html`
      <div class = "pm-PuzzleTime">
        <small class="pm-PuzzleTime-label">time:</small>
        <span class="pm-PuzzleTime-value">${data.time}</span>
      </div>
    `;
  }

  get data(): TemplateData
  {
    return{
      time: this.time,
    };
  }

  render()
  {
    render(this.template(this.data), this);
  }

  timer(time: number)
  {
    this.startTime = time;
    time = Math.ceil((new Date().getTime() - this.startTime) / 1000);
    this.render();
  }

  disconnectedCallBack()
  {
    streamService.unsubscribe("puzzle/time", this.instanceId);
  }
}

customElements.define(tag, PmPuzzleTime);
*/
