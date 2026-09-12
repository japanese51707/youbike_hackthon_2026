export default function TwinLayerExplain({ item }) {
  return (
    <div className="twin-layer-explain">
      <p className="twin-layer-explain-kicker">這張圖在分析什麼</p>
      <p>{item.reading}</p>
      <p className="twin-layer-explain-kicker">方法說明</p>
      <p>{item.info}</p>
    </div>
  );
}
