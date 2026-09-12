import { DesktopOutlined, MoonOutlined, SunOutlined } from "@ant-design/icons";
import { Segmented, Tooltip } from "antd";
import { useAppearance } from "../../theme/ThemeProvider.jsx";

export default function AppearanceControl() {
  const { preference, setPreference, storageError } = useAppearance();
  return <div className="appearance-control">
    <Segmented aria-label="外觀模式" value={preference} onChange={setPreference} options={[
      { value: "light", label: <span><SunOutlined /> <span>日光</span></span> },
      { value: "dark", label: <span><MoonOutlined /> <span>夜間</span></span> },
      { value: "system", label: <Tooltip title="跟隨裝置外觀"><span aria-label="跟隨系統"><DesktopOutlined /></span></Tooltip> },
    ]} />
    {storageError && <span role="status" className="appearance-note">外觀已套用；瀏覽器無法儲存偏好</span>}
  </div>;
}
